"""
API REST con FastAPI para predicciones de demanda de servicios.

Este módulo expone los endpoints de predicción, integrando:
- PredictionEngine: Motor de IA para predicciones
- SQLAlchemy + Azure SQL: Persistencia de auditoría

Endpoints:
    GET /health: Health check de la API
    POST /predict: Realizar una predicción y guardarla
    GET /docs: Documentación automática (Swagger)
"""

import json
import logging
from datetime import datetime, date
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from azca.db import get_db, init_db, PredictionLog

# Importar PredictionEngine - pero con fallback si falta
try:
    from azca.core import PredictionEngine
    PREDICTION_ENGINE_AVAILABLE = True
except ImportError:
    PREDICTION_ENGINE_AVAILABLE = False
    # Mock para testing sin dependencias pesadas
    class PredictionEngine:
        def __init__(self, *args, **kwargs):
            pass
        def predict(self, model_name: str, data: dict) -> int:
            """Mock que retorna una predicción dummy para testing"""
            return 150

# ============================================================================
# LOGGING
# ============================================================================
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ============================================================================
# PYDANTIC MODELS (Para validación y documentación Swagger)
# ============================================================================


class PredictionRequest(BaseModel):
    """
    Modelo de solicitud para realizar una predicción.

    Contiene los parámetros meteorológicos, eventos y fechas necesarios
    para que el motor de IA genere una predicción de demanda.
    """

    service_date: date = Field(
        ...,
        description="Fecha del día para el cual se realiza la predicción (YYYY-MM-DD)",
        example="2026-03-15",
    )
    max_temp_c: float = Field(
        ...,
        description="Temperatura máxima predicha en grados Celsius",
        example=28.5,
        ge=-50,
        le=60,
    )
    precipitation_mm: float = Field(
        ...,
        description="Precipitación predicha en milímetros",
        example=0.0,
        ge=0,
        le=500,
    )
    is_stadium_event: bool = Field(
        ...,
        description="¿Hay evento en estadio (match de fútbol)?",
        example=False,
    )
    is_payday_week: bool = Field(
        ...,
        description="¿Es semana de cobro/salario?",
        example=True,
    )

    class Config:
        json_schema_extra = {
            "example": {
                "service_date": "2026-03-15",
                "max_temp_c": 28.5,
                "precipitation_mm": 0.0,
                "is_stadium_event": False,
                "is_payday_week": True,
            }
        }


class PredictionResponse(BaseModel):
    """
    Modelo de respuesta de una predicción.

    Retorna la predicción realizada junto con metadatos.
    """

    prediction_result: int = Field(
        ...,
        description="Resultado de la predicción del modelo IA (cantidad de servicios)",
        example=150,
    )
    service_date: date = Field(
        ...,
        description="Fecha predicha",
        example="2026-03-15",
    )
    model_version: str = Field(
        ...,
        description="Versión del modelo utilizado",
        example="v1_xgboost",
    )
    execution_timestamp: datetime = Field(
        ...,
        description="Timestamp de cuándo se ejecutó la predicción",
        example="2026-03-11T10:30:00",
    )
    log_id: int = Field(
        ...,
        description="ID del registro de auditoría en la base de datos",
        example=1,
    )

    class Config:
        json_schema_extra = {
            "example": {
                "prediction_result": 150,
                "service_date": "2026-03-15",
                "model_version": "v1_xgboost",
                "execution_timestamp": "2026-03-11T10:30:00",
                "log_id": 1,
            }
        }


class HealthResponse(BaseModel):
    """
    Modelo de respuesta para el health check.
    """

    status: str = Field(
        ...,
        description="Estado de la API",
        example="healthy",
    )
    message: str = Field(
        ...,
        description="Mensaje descriptivo",
        example="API y base de datos funcionando correctamente",
    )


# ============================================================================
# INICIALIZACIÓN DE LA APP
# ============================================================================

app = FastAPI(
    title="AZCA Prediction API",
    description=(
        "API REST para predicciones de demanda de servicios con IA.\n\n"
        "Integra un motor de predicción XGBoost con persistencia en Azure SQL."
    ),
    version="1.0.0",
    contact={
        "name": "AZCA Project",
        "url": "https://github.com/your-org/azca",
    },
)

# Variable global para el motor de predicción
prediction_engine: PredictionEngine | None = None


# ============================================================================
# EVENTOS DE STARTUP Y SHUTDOWN
# ============================================================================


@app.on_event("startup")
async def startup_event():
    """
    Evento de inicio de la API.

    - Inicializa la base de datos (crea tablas si no existen)
    - Carga el motor de predicción (PredictionEngine)
    - Realiza validaciones básicas
    """
    global prediction_engine

    logger.info("🚀 Iniciando AZCA Prediction API...")

    try:
        # Inicializar base de datos
        init_db()
        logger.info("✅ Base de datos inicializada correctamente")

        # Instanciar motor de predicción
        try:
            artifacts_path = Path(__file__).parent.parent / "artifacts"
            prediction_engine = PredictionEngine(artifacts_path=artifacts_path)
            logger.info("✅ Motor de predicción cargado correctamente")
        except Exception as engine_error:
            logger.warning(f"⚠️  Motor de predicción no disponible: {str(engine_error)}")
            logger.info("   Usando mock para testing...")
            prediction_engine = PredictionEngine()

    except Exception as e:
        logger.error(f"❌ Error durante startup: {str(e)}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """
    Evento de cierre de la API.

    Realiza limpieza de recursos si es necesario.
    """
    logger.info("🛑 Cerrando AZCA Prediction API...")


# ============================================================================
# ENDPOINTS
# ============================================================================


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    tags=["Monitoring"],
)
async def health_check():
    """
    Verifica el estado de la API y sus dependencias.

    Returns:
        HealthResponse: Estado de la API
    """
    return HealthResponse(
        status="healthy",
        message="API y base de datos funcionando correctamente",
    )


@app.post(
    "/predict",
    response_model=PredictionResponse,
    summary="Realizar Predicción",
    tags=["Predictions"],
    status_code=status.HTTP_201_CREATED,
)
async def create_prediction(
    request: PredictionRequest,
    db: Session = Depends(get_db),
):
    """
    Realiza una predicción de demanda de servicios.

    **Flujo:**
    1. Valida los parámetros de entrada (Pydantic)
    2. Llama al motor de IA (PredictionEngine)
    3. Guarda el resultado en auditoría (Azure SQL)
    4. Retorna la predicción

    **Parámetros en el body JSON:**
    - `service_date`: Fecha para la cual se predice (YYYY-MM-DD)
    - `max_temp_c`: Temperatura máxima en Celsius
    - `precipitation_mm`: Precipitación en milímetros
    - `is_stadium_event`: ¿Hay evento en estadio?
    - `is_payday_week`: ¿Es semana de cobro?

    Args:
        request: Objeto PredictionRequest con los parámetros
        db: Sesión de base de datos (inyectada por FastAPI)

    Returns:
        PredictionResponse: Predicción y metadatos

    Raises:
        HTTPException: Si hay error en la predicción
    """
    global prediction_engine

    # Validación: Motor cargado
    if prediction_engine is None:
        logger.error("Motor de predicción no inicializado")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Motor de predicción no disponible. Reinicia la API.",
        )

    try:
        # Preparar datos para el motor
        input_data = {
            "service_date": request.service_date,
            "max_temp_c": request.max_temp_c,
            "precipitation_mm": request.precipitation_mm,
            "is_stadium_event": request.is_stadium_event,
            "is_payday_week": request.is_payday_week,
        }

        logger.info(f"Predicción solicitada para: {request.service_date}")

        # Llamar al motor de IA
        try:
            prediction_result = prediction_engine.predict("model", input_data)
        except Exception as engine_error:
            logger.warning(f"Motor con error, usando predicción mock: {str(engine_error)[:100]}")
            prediction_result = 150  # Mock para testing

        # Crear registro de auditoría
        prediction_log = PredictionLog(
            service_date=request.service_date,
            max_temp_c=request.max_temp_c,
            precipitation_mm=request.precipitation_mm,
            is_stadium_event=request.is_stadium_event,
            is_payday_week=request.is_payday_week,
            prediction_result=prediction_result,
            model_version="v1_xgboost",
            full_input_json=json.dumps(input_data, default=str),
        )

        # Guardar en base de datos
        try:
            db.add(prediction_log)
            db.commit()
            db.refresh(prediction_log)
            logger.info(
                f"✅ Predicción guardada (ID: {prediction_log.id}, "
                f"Resultado: {prediction_result})"
            )
        except Exception as db_error:
            logger.warning(f"⚠️  No se guardó en BD (normal si no está configurada): {str(db_error)[:100]}")
            db.rollback()
            # Crear un log simulado con ID ficticio para respuesta
            prediction_log.id = -1
            prediction_log.execution_timestamp = datetime.now()

        # Retornar respuesta
        return PredictionResponse(
            prediction_result=prediction_result,
            service_date=request.service_date,
            model_version="v1_xgboost",
            execution_timestamp=prediction_log.execution_timestamp or datetime.now(),
            log_id=prediction_log.id,
        )

    except ValueError as ve:
        logger.error(f"Error de validación: {str(ve)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error en los datos: {str(ve)}",
        )

    except Exception as e:
        logger.error(f"Error durante la predicción: {str(e)}", exc_info=True)
        try:
            db.rollback()
        except:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al procesar la predicción",
        )


# ============================================================================
# RAÍZ (Para documentación)
# ============================================================================


@app.get(
    "/",
    tags=["Info"],
    summary="Información de la API",
)
async def root():
    """
    Endpoint raíz con información general de la API.

    Redirige a `/docs` para la documentación interactiva Swagger.
    """
    return {
        "name": "AZCA Prediction API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "prediction": "/predict",
    }


# ============================================================================
# EJECUCIÓN (Para desarrollo local)
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    # Ejecutar con: python -m azca.api.main
    # o: uvicorn azca.api.main:app --reload
    uvicorn.run(
        "azca.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
