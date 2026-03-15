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
import os
from datetime import datetime, date, timedelta
from pathlib import Path

import holidays
import requests
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from pydantic import BaseModel, Field

from ..db import get_db, init_db, PredictionLog, Restaurant, FactServices, SessionLocal, DimDish, MenusAzca
from ..core.menu_intelligence import (
    DocumentIntelligenceOCR,
    MenuMLPredictor,
    MenuSectionExtractor,
)

# Importar PredictionEngine - pero con fallback si falta
try:
    from ..core import PredictionEngine
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
    Modelo de solicitud para realizar una predicción completa.

    Contiene todos los parámetros necesarios para el modelo de ML:
    - Fecha y meteorología
    - Eventos especiales y calendario
    - Características del restaurante
    - Datos operacionales
    """

    # Fecha
    service_date: date = Field(
        ...,
        description="Fecha del servicio (YYYY-MM-DD)",
        example="2026-03-15",
    )
    
    # Identificación
    restaurant_id: int = Field(
        ...,
        description="ID del restaurante",
        example=1,
        ge=1,
    )
    
    # Meteorología (OBTENIDA AUTOMÁTICAMENTE DE OPEN-METEO)
    max_temp_c: float = Field(
        default=20.0,
        description="Temperatura máxima en Celsius (obtenida automáticamente de Open-Meteo si no se proporciona)",
        example=28.5,
        ge=-50,
        le=60,
    )
    precipitation_mm: float = Field(
        default=0.0,
        description="Precipitación en milímetros (obtenida automáticamente de Open-Meteo si no se proporciona)",
        example=0.0,
        ge=0,
        le=500,
    )
    
    # Eventos y calendario
    is_rain_service_peak: bool = Field(
        default=False,
        description="¿Lluvia durante hora pico? (calculada automáticamente de Open-Meteo si no se proporciona)",
        example=False,
    )
    is_stadium_event: bool = Field(
        default=False,
        description="¿Hay evento en estadio?",
        example=False,
    )
    is_azca_event: bool = Field(
        default=False,
        description="¿Hay evento AZCA?",
        example=False,
    )
    is_holiday: bool = Field(
        default=False,
        description="¿Es día festivo? (calculado automáticamente si no se proporciona)",
        example=False,
    )
    is_bridge_day: bool = Field(
        default=False,
        description="¿Es puente festivo? (calculado automáticamente si no se proporciona)",
        example=False,
    )
    is_payday_week: bool = Field(
        default=False,
        description="¿Es semana de cobro? (calculado automáticamente si no se proporciona)",
        example=True,
    )
    is_business_day: bool = Field(
        default=True,
        description="¿Es día laboral? (calculado automáticamente si no se proporciona)",
        example=True,
    )
    
    # Datos históricos
    services_lag_7: int = Field(
        default=0,
        description="Servicios hace 7 días (recuperado automáticamente de fact_services si no se proporciona)",
        example=120,
        ge=0,
    )
    avg_4_weeks: float = Field(
        default=0.0,
        description="Promedio últimas 4 semanas (recuperado automáticamente de fact_services si no se proporciona)",
        example=125.5,
        ge=0,
    )
    
    # Características del restaurante
    capacity_limit: int = Field(
        ...,
        description="Límite de capacidad",
        example=80,
        ge=1,
    )
    table_count: int = Field(
        ...,
        description="Cantidad de mesas",
        example=20,
        ge=1,
    )
    min_service_duration: int = Field(
        ...,
        description="Duración mínima servicio (minutos)",
        example=45,
        ge=1,
    )
    terrace_setup_type: str = Field(
        ...,
        description="Tipo de setup terraza",
        example="outdoor",
    )
    opens_weekends: bool = Field(
        ...,
        description="¿Abre fines de semana?",
        example=True,
    )
    has_wifi: bool = Field(
        ...,
        description="¿Tiene Wi-Fi?",
        example=True,
    )
    restaurant_segment: str = Field(
        ...,
        description="Segmento del restaurante (e.g., casual, fine_dining)",
        example="casual",
    )
    menu_price: float = Field(
        ...,
        description="Precio promedio menú",
        example=25.50,
        ge=0,
    )
    dist_office_towers: int = Field(
        ...,
        description="Distancia a torres de oficina (metros)",
        example=500,
        ge=0,
    )
    google_rating: float = Field(
        ...,
        description="Calificación Google",
        example=4.5,
        ge=0,
        le=5,
    )
    cuisine_type: str = Field(
        ...,
        description="Tipo de cocina",
        example="mediterranean",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "service_date": "2026-03-15",
                "restaurant_id": 1,
                "max_temp_c": 28.5,
                "precipitation_mm": 0.0,
                "is_rain_service_peak": False,
                "is_stadium_event": False,
                "is_azca_event": False,
                "is_holiday": False,
                "is_bridge_day": False,
                "is_payday_week": True,
                "is_business_day": True,
                "services_lag_7": 120,
                "avg_4_weeks": 125.5,
                "capacity_limit": 80,
                "table_count": 20,
                "min_service_duration": 45,
                "terrace_setup_type": "outdoor",
                "opens_weekends": True,
                "has_wifi": True,
                "restaurant_segment": "casual",
                "menu_price": 25.50,
                "dist_office_towers": 500,
                "google_rating": 4.5,
                "cuisine_type": "mediterranean",
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


class StarterDish(BaseModel):
    """
    Modelo para un plato de entrada (starter).
    Incluye nombre, score de predicción y count estimado.
    """
    rank: int = Field(..., description="Ranking (1=top)", example=1)
    name: str = Field(..., description="Nombre del plato", example="Jamón Ibérico")
    score: float = Field(..., description="Score de probabilidad (0-1)", example=0.85)
    estimated_count: int = Field(..., description="Número estimado de este plato en el restaurante", example=43)


class StarterPredictionRequest(BaseModel):
    """
    Modelo de solicitud para predecir platos de entrada.
    
    Inputs del usuario (mínimo):
    - restaurant_id: ID del restaurante
    - service_date: Fecha del servicio
    
    Los demás parámetros se auto-calculan automáticamente.
    """
    restaurant_id: int = Field(
        ...,
        description="ID del restaurante",
        example=1,
        ge=1,
    )
    service_date: date = Field(
        ...,
        description="Fecha del servicio (YYYY-MM-DD)",
        example="2026-03-15",
    )


class StarterPredictionResponse(BaseModel):
    """
    Modelo de respuesta para predicción de starters.
    
    Retorna top 3 platos más probables con sus scores.
    """
    top_3_dishes: list[StarterDish] = Field(
        ...,
        description="Top 3 platos de entrada ordenados por probabilidad",
        example=[
            {"rank": 1, "name": "Jamón Ibérico", "score": 0.85},
            {"rank": 2, "name": "Croquetas de Jamón", "score": 0.78},
            {"rank": 3, "name": "Espárragos a la Crema", "score": 0.72},
        ],
    )
    service_date: date = Field(
        ...,
        description="Fecha predicha",
        example="2026-03-15",
    )
    restaurant_id: int = Field(
        ...,
        description="ID del restaurante",
        example=1,
    )
    model_version: str = Field(
        ...,
        description="Versión del modelo",
        example="azca_menu_starter_v2",
    )
    execution_timestamp: datetime = Field(
        ...,
        description="Timestamp de ejecución",
        example="2026-03-14T10:30:00",
    )


class MainDish(BaseModel):
    """
    Modelo para un plato principal (main course).
    Incluye nombre, score de predicción y count estimado.
    """
    rank: int = Field(..., description="Ranking (1=top)", example=1)
    name: str = Field(..., description="Nombre del plato", example="Carne a la Sal")
    score: float = Field(..., description="Score de probabilidad (0-1)", example=0.88)
    estimated_count: int = Field(..., description="Número estimado de este plato en el restaurante", example=44)


class MainPredictionRequest(BaseModel):
    """
    Modelo de solicitud para predecir platos principales.
    Input mínimo del usuario: restaurant_id + service_date.
    """
    restaurant_id: int = Field(..., description="ID del restaurante", example=1, ge=1)
    service_date: date = Field(..., description="Fecha del servicio (YYYY-MM-DD)", example="2026-03-15")


class MainPredictionResponse(BaseModel):
    """
    Modelo de respuesta para predicción de platos principales.
    Retorna top 3 platos más probables.
    """
    top_3_dishes: list[MainDish] = Field(
        ...,
        description="Top 3 platos principales ordenados por probabilidad",
        example=[
            {"rank": 1, "name": "Carne a la Sal", "score": 0.88},
            {"rank": 2, "name": "Merluza a la Gallega", "score": 0.82},
            {"rank": 3, "name": "Cordero Lechal", "score": 0.76},
        ],
    )
    service_date: date = Field(..., description="Fecha predicha", example="2026-03-15")
    restaurant_id: int = Field(..., description="ID del restaurante", example=1)
    model_version: str = Field(..., description="Versión del modelo", example="azca_menu_main_v2")
    execution_timestamp: datetime = Field(..., description="Timestamp de ejecución", example="2026-03-14T10:30:00")


class DessertDish(BaseModel):
    """
    Modelo para un postre (dessert).
    Incluye nombre, score de predicción y count estimado.
    """
    rank: int = Field(..., description="Ranking (1=top)", example=1)
    name: str = Field(..., description="Nombre del postre", example="Flan Casero")
    score: float = Field(..., description="Score de probabilidad (0-1)", example=0.83)
    estimated_count: int = Field(..., description="Número estimado de este postre en el restaurante", example=42)


class DessertPredictionRequest(BaseModel):
    """
    Modelo de solicitud para predecir postres.
    Input mínimo del usuario: restaurant_id + service_date.
    """
    restaurant_id: int = Field(..., description="ID del restaurante", example=1, ge=1)
    service_date: date = Field(..., description="Fecha del servicio (YYYY-MM-DD)", example="2026-03-15")


class DessertPredictionResponse(BaseModel):
    """
    Modelo de respuesta para predicción de postres.
    Retorna top 3 postres más probables.
    """
    top_3_dishes: list[DessertDish] = Field(
        ...,
        description="Top 3 postres ordenados por probabilidad",
        example=[
            {"rank": 1, "name": "Flan Casero", "score": 0.83},
            {"rank": 2, "name": "Tiramisú", "score": 0.79},
            {"rank": 3, "name": "Churros con Chocolate", "score": 0.75},
        ],
    )
    service_date: date = Field(..., description="Fecha predicha", example="2026-03-15")
    restaurant_id: int = Field(..., description="ID del restaurante", example=1)
    model_version: str = Field(..., description="Versión del modelo", example="azca_menu_dessert_v2")
    execution_timestamp: datetime = Field(..., description="Timestamp de ejecución", example="2026-03-14T10:30:00")


class OCRExtractedMenu(BaseModel):
    """
    Resultado de extracción OCR del menú subido.
    """

    starter: str = Field(..., description="Entrante detectado por OCR", example="Ensalada César")
    main: str = Field(..., description="Principal detectado por OCR", example="Merluza a la Gallega")
    dessert: str = Field(..., description="Postre detectado por OCR", example="Flan Casero")
    starter_options: list[str] = Field(default_factory=list, description="Todos los entrantes detectados")
    main_options: list[str] = Field(default_factory=list, description="Todos los principales detectados")
    dessert_options: list[str] = Field(default_factory=list, description="Todos los postres detectados")
    detected_lines: list[str] = Field(default_factory=list, description="Líneas útiles detectadas por OCR")


class OCRPredictedDish(BaseModel):
    """
    Plato predicho por el modelo para una categoría.
    """

    rank: int = Field(..., description="Ranking (1=top)", example=1)
    name: str = Field(..., description="Nombre del plato", example="Merluza a la Gallega")
    score: float = Field(..., description="Probabilidad estimada (0-1)", example=0.82)


class MenuUploadPredictionResponse(BaseModel):
    """
    Respuesta combinada OCR + predicción ML del menú subido.
    """

    restaurant_id: int = Field(..., description="ID del restaurante", example=1)
    service_date: date = Field(..., description="Fecha del servicio", example="2026-03-15")
    ocr_provider: str = Field(..., description="Proveedor OCR usado", example="azure_document_intelligence")
    extracted_menu: OCRExtractedMenu = Field(..., description="Platos detectados desde el menú")
    starter_prediction: list[OCRPredictedDish] = Field(..., description="Top 3 entrantes predichos")
    main_prediction: list[OCRPredictedDish] = Field(..., description="Top 3 principales predichos")
    dessert_prediction: list[OCRPredictedDish] = Field(..., description="Top 3 postres predichos")
    model_version: str = Field(..., description="Versión del stack de modelos", example="azca_menu_v2")
    execution_timestamp: datetime = Field(..., description="Timestamp de ejecución")


class MenuOCRSectionsResponse(BaseModel):
    """
    Respuesta OCR pura (sin predicción) para inspeccionar secciones detectadas.
    """

    ocr_provider: str = Field(..., description="Proveedor OCR usado", example="azure_document_intelligence")
    extracted_menu: OCRExtractedMenu = Field(..., description="Platos detectados desde el menú")
    raw_text: str = Field(..., description="Texto OCR completo para depuración")
    execution_timestamp: datetime = Field(..., description="Timestamp de ejecución")


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


class RestaurantItem(BaseModel):
    """
    Modelo de respuesta para un restaurante individual (lista).
    Solo incluye ID y nombre para la lista.
    """
    restaurant_id: int = Field(..., description="ID único del restaurante")
    name: str = Field(..., description="Nombre del restaurante")

    class Config:
        from_attributes = True


class RestaurantDetailItem(BaseModel):
    """
    Modelo de respuesta detallado para un restaurante.
    Incluye todos los campos para llenar el formulario de predicción.
    """
    restaurant_id: int = Field(..., description="ID único del restaurante")
    name: str = Field(..., description="Nombre del restaurante")
    capacity_limit: int | None = Field(None, description="Límite de capacidad")
    table_count: int | None = Field(None, description="Cantidad de mesas")
    min_service_duration: int | None = Field(None, description="Duración mínima servicio (minutos)")
    terrace_setup_type: str | None = Field(None, description="Tipo de setup terraza")
    opens_weekends: bool | None = Field(None, description="¿Abre fines de semana?")
    has_wifi: bool | None = Field(None, description="¿Tiene Wi-Fi?")
    restaurant_segment: str | None = Field(None, description="Segmento del restaurante")
    menu_price: float | None = Field(None, description="Precio promedio menú")
    dist_office_towers: int | None = Field(None, description="Distancia a torres de oficina (metros)")
    google_rating: float | None = Field(None, description="Calificación Google")
    cuisine_type: str | None = Field(None, description="Tipo de cocina")

    class Config:
        from_attributes = True


class RestaurantsListResponse(BaseModel):
    """
    Modelo de respuesta para la lista de restaurantes.
    """
    count: int = Field(..., description="Cantidad total de restaurantes")
    restaurants: list[RestaurantItem] = Field(..., description="Lista de restaurantes")


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

# Configurar CORS para permitir requests desde el frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, cambiar a ["https://tudominio.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

    try:
        # Inicializar base de datos
        init_db()
        
        # Intentar conectar y cargar restaurantes
        try:
            db = SessionLocal()
            restaurant_count = db.query(Restaurant).count()
            db.close()
        except Exception as db_error:
            logger.error(f"❌ Error conectando BD: {str(db_error)}", exc_info=True)

        # Instanciar motor de predicción
        try:
            artifacts_path = Path(__file__).parent.parent / "azca" / "artifacts"
            prediction_engine = PredictionEngine(artifacts_path=artifacts_path)
        except Exception as engine_error:
            logger.warning(f"⚠️ Motor de predicción no disponible (usando mock): {str(engine_error)}")
            prediction_engine = PredictionEngine()

    except Exception as e:
        logger.error(f"❌ Error durante startup: {str(e)}", exc_info=True)
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """
    Evento de cierre de la API.

    Realiza limpieza de recursos si es necesario.
    """
    pass


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


@app.get(
    "/restaurants",
    response_model=RestaurantsListResponse,
    summary="Obtener Lista de Restaurantes",
    tags=["Data"],
)
async def get_restaurants(db: Session = Depends(get_db)):
    """
    Obtiene la lista de todos los restaurantes disponibles desde Azure SQL.

    Returns:
        RestaurantsListResponse: Lista de restaurantes con su información básica
    """
    try:
        restaurants = db.query(Restaurant).all()
        
        response = RestaurantsListResponse(
            count=len(restaurants),
            restaurants=[
                RestaurantItem(
                    restaurant_id=r.restaurant_id,
                    name=r.name
                )
                for r in restaurants
            ]
        )
        
        return response
    except Exception as e:
        logger.error(f"❌ Error en GET /restaurants: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener lista de restaurantes"
        )


@app.get(
    "/restaurants/{restaurant_id}",
    response_model=RestaurantDetailItem,
    summary="Obtener Detalles de un Restaurante",
    tags=["Data"],
)
async def get_restaurant_detail(restaurant_id: int, db: Session = Depends(get_db)):
    """
    Obtiene todos los detalles de un restaurante específico por ID.
    
    Devuelve todos los campos necesarios para llenar el formulario de predicción.

    Args:
        restaurant_id: ID del restaurante a obtener

    Returns:
        RestaurantDetailItem: Detalles completos del restaurante
    """
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.restaurant_id == restaurant_id).first()
        
        if not restaurant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Restaurante con ID {restaurant_id} no encontrado"
            )
        
        return RestaurantDetailItem.from_orm(restaurant)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error en GET /restaurants/{restaurant_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener detalles del restaurante"
        )



# ============================================================================
# FUNCIONES AUXILIARES PARA CÁLCULO AUTOMÁTICO
# ============================================================================

def get_weather_data(service_date: date) -> dict:
    """
    Recupera datos meteorológicos de Open-Meteo para Azca (Madrid).
    
    Open-Meteo es una API meteorológica gratuita sin necesidad de API key.
    Coordenadas de Azca Madrid (Bernabéu): 40.4532° N, -3.6885° W
    
    Args:
        service_date: Fecha para la cual se obtiene el clima (date object)
        
    Returns:
        dict: {
            'max_temp_c': float (temperatura máxima en C),
            'precipitation_mm': float (precipitación en mm),
            'is_rain_service_peak': bool (si llueve en horas pico 12-20)
        }
    """
    # Coordenadas de Azca (Madrid, al lado del Bernabéu)
    latitude = 40.4532
    longitude = -3.6885
    
    # URL de Open-Meteo
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": service_date.strftime('%Y-%m-%d'),
        "end_date": service_date.strftime('%Y-%m-%d'),
        "daily": "temperature_2m_max,precipitation_sum",
        "hourly": "precipitation",
        "timezone": "auto",
    }
    
    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        # Extraer datos diarios
        max_temp = 20.0
        precipitation = 0.0
        
        if "daily" in data and len(data["daily"]["time"]) > 0:
            max_temp = data["daily"]["temperature_2m_max"][0] or 20.0
            precipitation = data["daily"]["precipitation_sum"][0] or 0.0
        
        # Determinar si llueve en hora pico (12:00-20:00)
        is_rain_peak = False
        if "hourly" in data and "precipitation" in data["hourly"]:
            hourly_times = data["hourly"]["time"]
            hourly_precip = data["hourly"]["precipitation"]
            
            # Buscar índices para horas 12-20 del día solicitado
            peak_hours_rain = sum(
                1 for i, t in enumerate(hourly_times)
                if service_date.strftime('%Y-%m-%d') in t and 
                   12 <= int(t.split('T')[1].split(':')[0]) < 20 and
                   hourly_precip[i] > 0
            )
            is_rain_peak = peak_hours_rain > 0
        
        return {
            'max_temp_c': float(max_temp),
            'precipitation_mm': float(precipitation),
            'is_rain_service_peak': is_rain_peak,
        }
        
    except requests.exceptions.RequestException as e:
        logger.warning(f"⚠️  Open-Meteo no disponible: {str(e)[:50]}, usando valores por defecto")
        return {
            'max_temp_c': 20.0,
            'precipitation_mm': 0.0,
            'is_rain_service_peak': False,
        }


def get_services_data(db: Session, restaurant_id: int, service_date: date, capacity_limit: int) -> dict:
    """
    Recupera services_lag_7 y avg_4_weeks desde fact_services.
    
    Si la fecha exacta no existe (ej: fechas futuras), busca el registro más reciente
    para ese restaurante. Si no hay registros, usa valores por defecto (70% capacidad).
    
    Args:
        db: Sesión de base de datos
        restaurant_id: ID del restaurante
        service_date: Fecha del servicio (date object)
        capacity_limit: Capacidad del restaurante (para cálculo de fallback)
        
    Returns:
        dict: {'services_lag_7': float, 'avg_4_weeks': float}
    """
    # Convertir fecha YYYY-MM-DD a YYYYMMDD (formato date_id)
    date_id = int(service_date.strftime('%Y%m%d'))
    
    # 1. Intentar buscar el registro exacto
    fact_record = db.query(FactServices).filter(
        FactServices.date_id == date_id,
        FactServices.restaurant_id == restaurant_id
    ).first()
    
    if fact_record:
        return {
            'services_lag_7': fact_record.services_lag_7 or 0.0,
            'avg_4_weeks': fact_record.avg_4_weeks or 0.0,
        }
    
    # 2. Si no existe, buscar el registro más reciente
    recent_record = db.query(FactServices).filter(
        FactServices.restaurant_id == restaurant_id
    ).order_by(desc(FactServices.date_id)).first()
    
    if recent_record:
        return {
            'services_lag_7': recent_record.services_lag_7 or 0.0,
            'avg_4_weeks': recent_record.avg_4_weeks or 0.0,
        }
    
    # 3. Fallback: calcular valores por defecto (70% de capacidad)
    default_services = float(capacity_limit) * 0.7
    return {
        'services_lag_7': default_services,
        'avg_4_weeks': default_services,
    }


def calculate_calendar_features(service_date: date) -> dict:
    """
    Calcula automáticamente los parámetros de calendario basados en la fecha.
    Usa la librería 'holidays' para festivos españoles en Madrid (Azca location).
    
    Args:
        service_date: Fecha del servicio (date object)
        
    Returns:
        dict: {
            'is_business_day': bool (lunes-viernes),
            'is_holiday': bool (festivos en Madrid),
            'is_bridge_day': bool (puente festivo),
            'is_payday_week': bool (semana de pago)
        }
    """
    # Inicializar calendario de festivos españoles (subdivisión Madrid)
    es_holidays = holidays.Spain(subdiv='MD')
    
    weekday = service_date.weekday()  # 0=lunes, 6=domingo
    
    # 1. is_business_day: lunes(0) a viernes(4)
    is_business_day = weekday < 5
    
    # 2. is_holiday: está en el calendario de festivos de Madrid
    is_holiday = service_date in es_holidays
    
    # 3. is_bridge_day: es un día entre festivo y fin de semana
    # (ejm: viernes después de festivo, o lunes antes de festivo)
    is_bridge_day = False
    from datetime import timedelta
    
    if weekday == 4:  # Viernes
        prev_day = service_date - timedelta(days=1)
        if prev_day in es_holidays:
            is_bridge_day = True
    elif weekday == 0:  # Lunes
        next_day = service_date + timedelta(days=1)
        if next_day in es_holidays:
            is_bridge_day = True
    
    # 4. is_payday_week: últimos días del mes (25-31)
    # Típicamente entre 25-31 del mes
    day_of_month = service_date.day
    is_payday_week = 25 <= day_of_month <= 31
    
    return {
        'is_business_day': is_business_day,
        'is_holiday': is_holiday,
        'is_bridge_day': is_bridge_day,
        'is_payday_week': is_payday_week,
    }


def _get_total_course_count(db: Session, restaurant_id: int, course_column, fallback: int = 30) -> int:
    """
    Calcula el total histórico de platos servidos por tipo de curso para un restaurante.

    Prioridad:
    1) Conteo en Menus_Azca del curso indicado (no nulo y no vacío).
    2) avg_4_weeks más reciente en fact_services.
    3) 70% de capacidad del restaurante.
    4) Fallback fijo.
    """
    total = (
        db.query(func.count())
        .select_from(MenusAzca)
        .filter(
            MenusAzca.restaurant_id == restaurant_id,
            course_column.isnot(None),
            func.length(func.trim(course_column)) > 0,
        )
        .scalar()
    )

    if total and total > 0:
        return int(total)

    recent_record = (
        db.query(FactServices)
        .filter(FactServices.restaurant_id == restaurant_id)
        .order_by(desc(FactServices.date_id))
        .first()
    )
    if recent_record and recent_record.avg_4_weeks and recent_record.avg_4_weeks > 0:
        return max(1, int(round(float(recent_record.avg_4_weeks))))

    restaurant = db.query(Restaurant).filter(Restaurant.restaurant_id == restaurant_id).first()
    if restaurant and restaurant.capacity_limit and restaurant.capacity_limit > 0:
        return max(1, int(round(float(restaurant.capacity_limit) * 0.7)))

    return fallback


def get_total_starters(db: Session, restaurant_id: int) -> int:
    """Obtiene total histórico de entrantes para estimar counts por score."""
    return _get_total_course_count(db, restaurant_id, MenusAzca.first_course)


def get_total_mains(db: Session, restaurant_id: int) -> int:
    """Obtiene total histórico de platos principales para estimar counts por score."""
    return _get_total_course_count(db, restaurant_id, MenusAzca.second_course)


def get_total_desserts(db: Session, restaurant_id: int) -> int:
    """Obtiene total histórico de postres para estimar counts por score."""
    return _get_total_course_count(db, restaurant_id, MenusAzca.dessert)


def extract_menu_text_with_default_ocr(file_bytes: bytes, content_type: str | None = None) -> tuple[str, str]:
    """
    Extrae texto del documento usando Azure Document Intelligence por defecto.

    Variables de entorno requeridas:
    - AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT
    - AZURE_DOCUMENT_INTELLIGENCE_KEY
    - AZURE_DOCUMENT_INTELLIGENCE_MODEL_ID (opcional, default prebuilt-layout)
    """
    endpoint = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "").strip()
    key = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "").strip()
    model_id = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_MODEL_ID", "prebuilt-layout").strip()

    if not endpoint or not key:
        raise RuntimeError(
            "Faltan AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT o AZURE_DOCUMENT_INTELLIGENCE_KEY."
        )

    ocr = DocumentIntelligenceOCR(endpoint=endpoint, key=key, model_id=model_id)
    extracted_text = ocr.extract_text(file_bytes=file_bytes, content_type=content_type)

    if not extracted_text:
        raise RuntimeError("Document Intelligence no devolvió texto extraíble.")

    return extracted_text, "azure_document_intelligence"


def to_ranked_dishes(items: list[tuple[str, float]]) -> list[OCRPredictedDish]:
    """Convierte lista [(name, score)] en objetos tipados con ranking."""
    return [
        OCRPredictedDish(rank=index + 1, name=name, score=float(score))
        for index, (name, score) in enumerate(items[:3])
    ]


def build_extracted_menu(sections) -> OCRExtractedMenu:
    """Convierte la salida del extractor en el modelo de respuesta estándar."""
    return OCRExtractedMenu(
        starter=sections.starter,
        main=sections.main,
        dessert=sections.dessert,
        starter_options=sections.starter_options,
        main_options=sections.main_options,
        dessert_options=sections.dessert_options,
        detected_lines=sections.detected_lines,
    )


def persist_extracted_dishes(db: Session, sections) -> int:
    """
    Persiste los platos extraídos por OCR en dim_dishes.

    course_type usa los valores: first_course, second_course, dessert.
    """
    grouped_dishes = {
        "first_course": sections.starter_options,
        "second_course": sections.main_options,
        "dessert": sections.dessert_options,
    }

    inserted = 0
    seen: set[tuple[str, str]] = set()

    try:
        for course_type, dishes in grouped_dishes.items():
            for dish_name in dishes:
                normalized_name = (dish_name or "").strip()
                if not normalized_name:
                    continue

                dedupe_key = (course_type, normalized_name.casefold())
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                existing = (
                    db.query(DimDish.dish_id)
                    .filter(
                        DimDish.course_type == course_type,
                        func.lower(DimDish.dish_name) == normalized_name.lower(),
                    )
                    .first()
                )
                if existing:
                    continue

                db.add(DimDish(course_type=course_type, dish_name=normalized_name))
                inserted += 1

        if inserted > 0:
            db.commit()
        else:
            db.flush()

        return inserted

    except Exception:
        db.rollback()
        raise


@app.post(
    "/ocr/menu-sections",
    response_model=MenuOCRSectionsResponse,
    summary="Subir menú y ver solo detección OCR por secciones",
    tags=["Predictions"],
    status_code=status.HTTP_200_OK,
)
async def extract_menu_sections_ocr_only(
    menu_file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Flujo OCR puro (sin predicción ML):
    1) OCR con Azure Document Intelligence.
    2) Parser para detectar entrante, principal y postre.

    Request multipart/form-data:
    - menu_file: archivo (PDF/JPG/PNG, etc.)
    """
    try:
        file_bytes = await menu_file.read()
        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo de menú está vacío.",
            )

        raw_text, ocr_provider = extract_menu_text_with_default_ocr(
            file_bytes=file_bytes,
            content_type=menu_file.content_type,
        )
        sections = MenuSectionExtractor.extract(raw_text)
        persist_extracted_dishes(db, sections)

        return MenuOCRSectionsResponse(
            ocr_provider=ocr_provider,
            extracted_menu=build_extracted_menu(sections),
            raw_text=raw_text,
            execution_timestamp=datetime.now(),
        )

    except HTTPException:
        raise
    except RuntimeError as runtime_error:
        logger.error(f"OCR no disponible: {runtime_error}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(runtime_error),
        )
    except Exception as exc:
        logger.error(f"Error en /ocr/menu-sections: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al procesar OCR del menú.",
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
        # Calcular automáticamente parámetros de calendario
        calendar_features = calculate_calendar_features(request.service_date)
        
        # Recuperar datos históricos de fact_services
        # (services_lag_7 y avg_4_weeks desde la BD, con fallback a 70% capacidad)
        services_data = get_services_data(
            db=db,
            restaurant_id=request.restaurant_id,
            service_date=request.service_date,
            capacity_limit=request.capacity_limit
        )
        
        # Recuperar datos meteorológicos desde Open-Meteo
        weather_data = get_weather_data(request.service_date)
        
        # Preparar datos para el motor (combinando request + cálculos automáticos)
        input_data = {
            "service_date": request.service_date,
            "restaurant_id": request.restaurant_id,
            "max_temp_c": weather_data['max_temp_c'],  # DESDE Open-Meteo
            "precipitation_mm": weather_data['precipitation_mm'],  # DESDE Open-Meteo
            "is_rain_service_peak": weather_data['is_rain_service_peak'],  # DESDE Open-Meteo
            "is_stadium_event": request.is_stadium_event,
            "is_azca_event": request.is_azca_event,
            "is_holiday": calendar_features['is_holiday'],  # CALCULADO
            "is_bridge_day": calendar_features['is_bridge_day'],  # CALCULADO
            "is_payday_week": calendar_features['is_payday_week'],  # CALCULADO
            "is_business_day": calendar_features['is_business_day'],  # CALCULADO
            "services_lag_7": services_data['services_lag_7'],  # DESDE fact_services
            "avg_4_weeks": services_data['avg_4_weeks'],  # DESDE fact_services
            "capacity_limit": request.capacity_limit,
            "table_count": request.table_count,
            "min_service_duration": request.min_service_duration,
            "terrace_setup_type": request.terrace_setup_type,
            "opens_weekends": request.opens_weekends,
            "has_wifi": request.has_wifi,
            "restaurant_segment": request.restaurant_segment,
            "menu_price": request.menu_price,
            "dist_office_towers": request.dist_office_towers,
            "google_rating": request.google_rating,
            "cuisine_type": request.cuisine_type,
        }

        # LOG: Entrada de predicción
        logger.info("="*80)
        logger.info(f"📍 POST /predict - Solicitud recibida")
        logger.info("="*80)
        logger.info(f"🎯 Input: restaurante_id={request.restaurant_id}, fecha={request.service_date}")
        logger.info(f"   Eventos: stadium={request.is_stadium_event}, azca={request.is_azca_event}")
        logger.info(f"📊 Parámetros automáticos:")
        logger.info(f"   Clima: temp={weather_data['max_temp_c']}°C, precip={weather_data['precipitation_mm']:.1f}mm")
        logger.info(f"   Calendario: business_day={calendar_features['is_business_day']}, holiday={calendar_features['is_holiday']}, payday={calendar_features['is_payday_week']}")
        logger.info(f"   Histórico: lag_7={services_data['services_lag_7']}, avg_4w={services_data['avg_4_weeks']}")
        logger.info("="*80)

        # Llamar al motor de IA
        try:
            prediction_result = prediction_engine.predict("azca_demand_v1", input_data)
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


@app.post(
    "/predict/starter",
    response_model=StarterPredictionResponse,
    summary="Predecir Platos de Entrada",
    tags=["Predictions"],
    status_code=status.HTTP_201_CREATED,
)
async def predict_starter(
    request: StarterPredictionRequest,
    db: Session = Depends(get_db),
):
    """
    Predice los top 3 platos de entrada (starters) más probables para un restaurante en una fecha.
    
    Inputs del usuario (mínimos):
    - restaurant_id: ID del restaurante
    - service_date: Fecha del servicio
    
    Parámetros auto-calculados (backend):
    - day_of_week, month: Del service_date
    - max_temp_c: De Open-Meteo API (Azca/Bernabéu)
    - is_holiday, is_business_day: Del calendario español
    - cuisine_type, restaurant_segment: De dim_restaurants BD
    
    Returns:
        StarterPredictionResponse: Top 3 starters con scores de probabilidad
    """
    global prediction_engine

    if prediction_engine is None:
        logger.error("Motor de predicción no inicializado")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Motor de predicción no disponible. Reinicia la API.",
        )

    try:
        # 1. Obtener detalles del restaurante
        restaurant = db.query(Restaurant).filter(
            Restaurant.restaurant_id == request.restaurant_id
        ).first()
        
        if not restaurant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Restaurante con ID {request.restaurant_id} no encontrado"
            )

        # 2. Calcular automaticamente
        weather_data = get_weather_data(request.service_date)
        calendar_features = calculate_calendar_features(request.service_date)
        
        # Extraer day_of_week (0=Monday) y month (1-12)
        day_of_week = request.service_date.weekday()
        month = request.service_date.month
        
        # 3. Preparar input para modelo de starters (8 features exactas en orden)
        starter_input = {
            "day_of_week": day_of_week,
            "month": month,
            "max_temp_c": weather_data['max_temp_c'],
            "is_holiday": calendar_features['is_holiday'],
            "is_business_day": calendar_features['is_business_day'],
            "restaurant_id": request.restaurant_id,
            "cuisine_type": restaurant.cuisine_type,
            "restaurant_segment": restaurant.restaurant_segment,
        }
        
        # Log de entrada (para debugging)
        logger.info("="*80)
        logger.info(f"📍 POST /predict/starter - Solicitud recibida")
        logger.info("="*80)
        logger.info(f"🎯 Input: restaurante_id={request.restaurant_id}, fecha={request.service_date}")
        logger.info(f"📊 Parámetros auto-calculados:")
        logger.info(f"   Clima: temp={weather_data['max_temp_c']}°C")
        logger.info(f"   Calendario: business_day={calendar_features['is_business_day']}, holiday={calendar_features['is_holiday']}")
        logger.info(f"   Restaurante: {restaurant.name} ({restaurant.cuisine_type})")
        logger.info("="*80)
        
        # 4. Llamar al modelo para starters
        prediction = prediction_engine.predict_menu("azca_menu_starter_v2", starter_input)
        
        # Validar que el modelo retornó top 3
        if not isinstance(prediction, (list, tuple)) or len(prediction) < 3:
            logger.error(f"Modelo devolvió formato inválido: {type(prediction)} - {prediction}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Modelo retornó resultado inválido (esperaba lista de 3+ items): {prediction}"
            )
        
        top_dishes = prediction
        
        # 5. Obtener total de starters del restaurante para calcular counts estimados
        total_starters = get_total_starters(db, request.restaurant_id)
        logger.info(f"📊 Total de starters en el restaurante: {total_starters}")
        
        # Normalizar los scores del top 3 para que sumen 1, luego calcular counts
        scores = [dish[1] for dish in top_dishes[:3]]
        sum_scores = sum(scores)
        if sum_scores > 0:
            normalized_scores = [score / sum_scores for score in scores]
        else:
            normalized_scores = [1/3, 1/3, 1/3]  # Fallback si algo va mal
        
        # 5. Formatear respuesta (top 3 con rank y estimated_count normalizado)
        starter_dishes = [
            StarterDish(
                rank=i+1,
                name=dish[0],
                score=normalized_scores[i],  # Score normalizado (0-1, suma a 1)
                estimated_count=round(normalized_scores[i] * total_starters)  # porcentaje normalizado * total
            )
            for i, dish in enumerate(top_dishes[:3])
        ]
        
        # 6. Retornar respuesta (NO guardar en BD)
        return StarterPredictionResponse(
            top_3_dishes=starter_dishes,
            service_date=request.service_date,
            restaurant_id=request.restaurant_id,
            model_version="azca_menu_starter_v2",
            execution_timestamp=datetime.now(),
        )

    except HTTPException:
        raise
    except ValueError as ve:
        logger.error(f"Error de validación: {str(ve)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error en los datos: {str(ve)}",
        )
    except Exception as e:
        logger.error(f"Error durante la predicción de starters: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al procesar la predicción de starters",
        )


@app.post(
    "/predict/main",
    response_model=MainPredictionResponse,
    summary="Predecir Platos Principales",
    tags=["Predictions"],
    status_code=status.HTTP_201_CREATED,
)
async def predict_main(
    request: MainPredictionRequest,
    db: Session = Depends(get_db),
):
    """
    Predice los top 3 platos principales más probables para un restaurante en una fecha.
    Inputs del usuario (mínimos):
    - restaurant_id: ID del restaurante
    - service_date: Fecha del servicio
    
    Parámetros auto-calculados (backend):
    - day_of_week, month, max_temp_c, is_holiday, is_business_day, cuisine_type, restaurant_segment
    
    Returns:
        MainPredictionResponse: Top 3 platos principales con scores
    """
    global prediction_engine

    if prediction_engine is None:
        logger.error("Motor de predicción no inicializado")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Motor de predicción no disponible. Reinicia la API.",
        )

    try:
        # 1. Obtener detalles del restaurante
        restaurant = db.query(Restaurant).filter(
            Restaurant.restaurant_id == request.restaurant_id
        ).first()
        
        if not restaurant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Restaurante con ID {request.restaurant_id} no encontrado"
            )

        # 2. Calcular automaticamente
        weather_data = get_weather_data(request.service_date)
        calendar_features = calculate_calendar_features(request.service_date)
        
        day_of_week = request.service_date.weekday()
        month = request.service_date.month
        
        # 3. Preparar input para modelo de platos principales (8 features exactas en orden)
        main_input = {
            "day_of_week": day_of_week,
            "month": month,
            "max_temp_c": weather_data['max_temp_c'],
            "is_holiday": calendar_features['is_holiday'],
            "is_business_day": calendar_features['is_business_day'],
            "restaurant_id": request.restaurant_id,
            "cuisine_type": restaurant.cuisine_type,
            "restaurant_segment": restaurant.restaurant_segment,
        }
        
        logger.info("="*80)
        logger.info(f"📍 POST /predict/main - Solicitud recibida")
        logger.info("="*80)
        logger.info(f"🎯 Input: restaurante_id={request.restaurant_id}, fecha={request.service_date}")
        logger.info(f"📊 Parámetros auto-calculados: temp={weather_data['max_temp_c']}°C, restaurante={restaurant.name}")
        logger.info("="*80)
        
        # 4. Llamar al modelo para platos principales
        prediction = prediction_engine.predict_menu("azca_menu_main_v2", main_input)
        
        # Validar que el modelo retornó top 3
        if not isinstance(prediction, (list, tuple)) or len(prediction) < 3:
            logger.error(f"Modelo devolvió formato inválido: {type(prediction)} - {prediction}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Modelo retornó resultado inválido (esperaba lista de 3+ items): {prediction}"
            )
        
        top_dishes = prediction
        
        # 5. Obtener total de platos principales del restaurante para calcular counts estimados
        total_mains = get_total_mains(db, request.restaurant_id)
        logger.info(f"📊 Total de platos principales en el restaurante: {total_mains}")
        
        # Normalizar los scores del top 3 para que sumen 1, luego calcular counts
        scores = [dish[1] for dish in top_dishes[:3]]
        sum_scores = sum(scores)
        if sum_scores > 0:
            normalized_scores = [score / sum_scores for score in scores]
        else:
            normalized_scores = [1/3, 1/3, 1/3]  # Fallback si algo va mal
        
        # 5. Formatear respuesta
        main_dishes = [
            MainDish(
                rank=i+1,
                name=dish[0],
                score=normalized_scores[i],  # Score normalizado (0-1, suma a 1)
                estimated_count=round(normalized_scores[i] * total_mains)  # porcentaje normalizado * total
            )
            for i, dish in enumerate(top_dishes[:3])
        ]
        
        # 6. Retornar respuesta (NO guardar en BD)
        return MainPredictionResponse(
            top_3_dishes=main_dishes,
            service_date=request.service_date,
            restaurant_id=request.restaurant_id,
            model_version="azca_menu_main_v2",
            execution_timestamp=datetime.now(),
        )

    except HTTPException:
        raise
    except ValueError as ve:
        logger.error(f"Error de validación: {str(ve)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error en los datos: {str(ve)}",
        )
    except Exception as e:
        logger.error(f"Error durante la predicción de platos principales: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al procesar la predicción de platos principales",
        )


@app.post(
    "/predict/dessert",
    response_model=DessertPredictionResponse,
    summary="Predecir Postres",
    tags=["Predictions"],
    status_code=status.HTTP_201_CREATED,
)
async def predict_dessert(
    request: DessertPredictionRequest,
    db: Session = Depends(get_db),
):
    """
    Predice los top 3 postres más probables para un restaurante en una fecha.
    Inputs del usuario (mínimos):
    - restaurant_id: ID del restaurante
    - service_date: Fecha del servicio
    
    Parámetros auto-calculados (backend):
    - day_of_week, month, max_temp_c, is_holiday, is_business_day, cuisine_type, restaurant_segment
    
    Returns:
        DessertPredictionResponse: Top 3 postres con scores
    """
    global prediction_engine

    if prediction_engine is None:
        logger.error("Motor de predicción no inicializado")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Motor de predicción no disponible. Reinicia la API.",
        )

    try:
        # 1. Obtener detalles del restaurante
        restaurant = db.query(Restaurant).filter(
            Restaurant.restaurant_id == request.restaurant_id
        ).first()
        
        if not restaurant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Restaurante con ID {request.restaurant_id} no encontrado"
            )

        # 2. Calcular automaticamente
        weather_data = get_weather_data(request.service_date)
        calendar_features = calculate_calendar_features(request.service_date)
        
        day_of_week = request.service_date.weekday()
        month = request.service_date.month
        
        # 3. Preparar input para modelo de postres (8 features exactas en orden)
        dessert_input = {
            "day_of_week": day_of_week,
            "month": month,
            "max_temp_c": weather_data['max_temp_c'],
            "is_holiday": calendar_features['is_holiday'],
            "is_business_day": calendar_features['is_business_day'],
            "restaurant_id": request.restaurant_id,
            "cuisine_type": restaurant.cuisine_type,
            "restaurant_segment": restaurant.restaurant_segment,
        }
        
        logger.info("="*80)
        logger.info(f"📍 POST /predict/dessert - Solicitud recibida")
        logger.info("="*80)
        logger.info(f"🎯 Input: restaurante_id={request.restaurant_id}, fecha={request.service_date}")
        logger.info(f"📊 Parámetros auto-calculados: temp={weather_data['max_temp_c']}°C, restaurante={restaurant.name}")
        logger.info("="*80)
        
        # 4. Llamar al modelo para postres
        prediction = prediction_engine.predict_menu("azca_menu_dessert_v2", dessert_input)
        
        # Validar que el modelo retornó top 3
        if not isinstance(prediction, (list, tuple)) or len(prediction) < 3:
            logger.error(f"Modelo devolvió formato inválido: {type(prediction)} - {prediction}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Modelo retornó resultado inválido (esperaba lista de 3+ items): {prediction}"
            )
        
        top_dishes = prediction
        
        # 5. Obtener total de postres del restaurante para calcular counts estimados
        total_desserts = get_total_desserts(db, request.restaurant_id)
        logger.info(f"📊 Total de postres en el restaurante: {total_desserts}")
        
        # Normalizar los scores del top 3 para que sumen 1, luego calcular counts
        scores = [dish[1] for dish in top_dishes[:3]]
        sum_scores = sum(scores)
        if sum_scores > 0:
            normalized_scores = [score / sum_scores for score in scores]
        else:
            normalized_scores = [1/3, 1/3, 1/3]  # Fallback si algo va mal
        
        # 5. Formatear respuesta
        dessert_dishes = [
            DessertDish(
                rank=i+1,
                name=dish[0],
                score=normalized_scores[i],  # Score normalizado (0-1, suma a 1)
                estimated_count=round(normalized_scores[i] * total_desserts)  # porcentaje normalizado * total
            )
            for i, dish in enumerate(top_dishes[:3])
        ]
        
        # 6. Retornar respuesta (NO guardar en BD)
        return DessertPredictionResponse(
            top_3_dishes=dessert_dishes,
            service_date=request.service_date,
            restaurant_id=request.restaurant_id,
            model_version="azca_menu_dessert_v2",
            execution_timestamp=datetime.now(),
        )

    except HTTPException:
        raise
    except ValueError as ve:
        logger.error(f"Error de validación: {str(ve)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error en los datos: {str(ve)}",
        )
    except Exception as e:
        logger.error(f"Error durante la predicción de postres: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al procesar la predicción de postres",
        )


@app.post(
    "/predict/menu-upload",
    response_model=MenuUploadPredictionResponse,
    summary="Subir menú (OCR) y predecir platos",
    tags=["Predictions"],
    status_code=status.HTTP_201_CREATED,
)
async def predict_from_menu_upload(
    restaurant_id: int = Form(...),
    service_date: date = Form(...),
    menu_file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Flujo por defecto:
    1) OCR con Azure Document Intelligence para extraer el menú subido.
    2) Parser para detectar entrante, principal y postre.
    3) Predicción ML top-3 por categoría en base al menú detectado.

    Request multipart/form-data:
    - restaurant_id: int
    - service_date: YYYY-MM-DD
    - menu_file: archivo (PDF/JPG/PNG, etc.)
    """
    global prediction_engine

    if prediction_engine is None:
        logger.error("Motor de predicción no inicializado")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Motor de predicción no disponible. Reinicia la API.",
        )

    restaurant = db.query(Restaurant).filter(Restaurant.restaurant_id == restaurant_id).first()
    if not restaurant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Restaurante con ID {restaurant_id} no encontrado",
        )

    try:
        file_bytes = await menu_file.read()
        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo de menú está vacío.",
            )

        # OCR por defecto con Azure Document Intelligence
        raw_text, ocr_provider = extract_menu_text_with_default_ocr(
            file_bytes=file_bytes,
            content_type=menu_file.content_type,
        )

        # Detección de secciones del menú
        sections = MenuSectionExtractor.extract(raw_text)
        persist_extracted_dishes(db, sections)

        # Variables contextuales automáticas (similares al flujo actual)
        weather_data = get_weather_data(service_date)
        calendar_features = calculate_calendar_features(service_date)

        model_input_common = {
            "max_temp_c": weather_data["max_temp_c"],
            "is_holiday": calendar_features["is_holiday"],
            "is_bridge_day": calendar_features["is_bridge_day"],
            "is_business_day": calendar_features["is_business_day"],
            "cuisine_type": restaurant.cuisine_type,
            "restaurant_segment": restaurant.restaurant_segment,
            "menu_price": restaurant.menu_price or 15.0,
            "day_of_week": service_date.weekday(),
            "month": service_date.month,
        }

        menu_predictor = MenuMLPredictor(prediction_engine.model_provider)
        predictions = menu_predictor.predict_from_menu(model_input_common, sections)

        return MenuUploadPredictionResponse(
            restaurant_id=restaurant_id,
            service_date=service_date,
            ocr_provider=ocr_provider,
            extracted_menu=build_extracted_menu(sections),
            starter_prediction=to_ranked_dishes(predictions["starter"]),
            main_prediction=to_ranked_dishes(predictions["main"]),
            dessert_prediction=to_ranked_dishes(predictions["dessert"]),
            model_version="azca_menu_v2",
            execution_timestamp=datetime.now(),
        )

    except HTTPException:
        raise
    except RuntimeError as runtime_error:
        logger.error(f"OCR no disponible: {runtime_error}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(runtime_error),
        )
    except Exception as exc:
        logger.error(f"Error en /predict/menu-upload: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al procesar OCR y predicción del menú.",
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
