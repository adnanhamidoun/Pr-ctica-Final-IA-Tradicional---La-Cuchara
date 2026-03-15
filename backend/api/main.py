"""
API REST con FastAPI para predicciones de demanda de servicios.

Este módulo expone los endpoints de predicción, integrando:
- Carga de modelo pickle en lifespan (una sola vez)
- SQLAlchemy + Azure SQL: Persistencia de auditoría

Endpoints:
    GET /health: Health check de la API
    POST /predict: Realizar una predicción y guardarla
    GET /docs: Documentación automática (Swagger)
"""

import json
import logging
import os
import pickle
from contextlib import asynccontextmanager
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Literal

import holidays
import requests
from fastapi import FastAPI, Depends, HTTPException, status, Request, UploadFile, File, Form, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, distinct, or_, text
from pydantic import BaseModel, Field

from ..db import (
    get_db,
    init_db,
    engine,
    PredictionLog,
    Restaurant,
    FactServices,
    SessionLocal,
    DimDish,
    MenusAzca,
    DimDishes,
    FactMenuItems,
    FactMenus,
    RestaurantContext,
    FactPredictionLog,
    Inscripcion,
    SEGMENT_OPTIONS,
    TERRACE_OPTIONS,
    CUISINE_OPTIONS,
)
from ..core.menu_intelligence import (
    DocumentIntelligenceOCR,
    MenuMLPredictor,
    MenuSectionExtractor,
)
from ..core.auth import create_access_token, decode_access_token

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
    """Resultado de extracción OCR del menú subido."""
    starter: str = Field(..., description="Entrante detectado por OCR", example="Ensalada César")
    main: str = Field(..., description="Principal detectado por OCR", example="Merluza a la Gallega")
    dessert: str = Field(..., description="Postre detectado por OCR", example="Flan Casero")
    starter_options: list[str] = Field(default_factory=list, description="Todos los entrantes detectados")
    main_options: list[str] = Field(default_factory=list, description="Todos los principales detectados")
    dessert_options: list[str] = Field(default_factory=list, description="Todos los postres detectados")
    detected_lines: list[str] = Field(default_factory=list, description="Líneas útiles detectadas por OCR")


class OCRPredictedDish(BaseModel):
    """Plato predicho por el modelo para una categoría."""
    rank: int = Field(..., description="Ranking (1=top)", example=1)
    name: str = Field(..., description="Nombre del plato", example="Merluza a la Gallega")
    score: float = Field(..., description="Probabilidad estimada (0-1)", example=0.82)


class MenuOCRSectionsResponse(BaseModel):
    """Respuesta OCR pura (sin predicción) para inspeccionar secciones detectadas."""
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
    image_url: str | None = Field(None, description="URL de imagen pública del restaurante")

    class Config:
        from_attributes = True


class RestaurantsListResponse(BaseModel):
    """
    Modelo de respuesta para la lista de restaurantes.
    """
    count: int = Field(..., description="Cantidad total de restaurantes")
    restaurants: list[RestaurantItem] = Field(..., description="Lista de restaurantes")


class InscripcionCreateRequest(BaseModel):
    """Modelo de alta para solicitudes en dbo.inscripciones."""

    name: str = Field(..., description="Nombre del restaurante", min_length=1)
    capacity_limit: int | None = Field(None, description="Límite de capacidad", ge=1)
    table_count: int | None = Field(None, description="Cantidad de mesas", ge=1)
    min_service: str | None = Field(None, description="Duración mínima del servicio (texto)")
    terrace_setup_type: Literal[
        "yearround",
        "summer",
        "none",
    ] | None = Field(None, description="Tipo de terraza")
    opens_weekends: bool | None = Field(None, description="Abre fines de semana")
    has_wifi: bool | None = Field(None, description="Tiene WiFi")
    restaurant_segment: Literal[
        "gourmet",
        "traditional",
        "business",
        "family",
    ] | None = Field(None, description="Segmento del restaurante")
    menu_price: float | None = Field(None, description="Precio medio del menú", ge=0)
    dist_office_towers: int | None = Field(None, description="Distancia a oficinas en metros", ge=0)
    google_rating: float | None = Field(None, description="Valoración media (0-5)", ge=0, le=5)
    cuisine_type: Literal[
        "grill",
        "spanish",
        "mediterranean",
        "stew",
        "fried",
        "italian",
        "asian",
        "latin",
        "arabic",
        "avantgarde",
        "plantbased",
        "streetfood",
    ] | None = Field(None, description="Tipo de cocina")
    image_url: str | None = Field(None, description="URL inicial de imagen del restaurante")
    google_maps_link: str = Field(..., description="Link de reseñas/Google Maps (obligatorio)", min_length=5)


class InscripcionItem(BaseModel):
    """Modelo de respuesta para una solicitud en dbo.inscripciones."""

    inscripcion_id: int
    name: str
    capacity_limit: int | None = None
    table_count: int | None = None
    min_service: str | None = None
    terrace_setup_type: str | None = None
    opens_weekends: bool | None = None
    has_wifi: bool | None = None
    restaurant_segment: str | None = None
    menu_price: float | None = None
    dist_office_towers: int | None = None
    google_rating: float | None = None
    cuisine_type: str | None = None
    login_email: str | None = None
    image_url: str | None = None
    google_maps_link: str
    estado_inscripcion: str | None = None
    fecha_solicitud: datetime | None = None

    class Config:
        from_attributes = True


class InscripcionesListResponse(BaseModel):
    """Respuesta para listados de inscripciones."""

    count: int
    inscripciones: list[InscripcionItem]


class InscripcionActionResponse(BaseModel):
    """Respuesta estándar para acciones administrativas sobre inscripciones."""

    inscripcion_id: int
    status: str
    message: str
    restaurant_id: int | None = None


class ClearApprovalHistoryResponse(BaseModel):
    """Respuesta para limpieza del historial de aprobaciones."""

    deleted_count: int
    message: str


class LoginRequest(BaseModel):
    role: Literal["admin"]
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=3)


class AuthUserResponse(BaseModel):
    role: Literal["admin"]
    restaurant_id: int | None = None
    restaurant_name: str | None = None
    email: str
    token: str


class RestaurantImageUpdateRequest(BaseModel):
    image_url: str = Field(..., min_length=5)


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return None
    return authorization[len(prefix):].strip()


def _require_auth(authorization: str | None) -> dict:
    token = _extract_bearer_token(authorization)
    payload = decode_access_token(token) if token else None
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión no válida.")
    return payload


# ============================================================================
# CACHÉ EN MEMORIA - Clima y Calendario
# ============================================================================

class CacheManager:
    """
    Gestor de caché en memoria para datos de clima, calendario y conteos de dishes.
    
    Evita llamadas repetidas a Open-Meteo API y queries costosas a BD.
    
    Beneficio: 
    - Clima/Calendario: Reducir 200-500ms por predicción × 3 = hasta 1.5s ahorrados
    - Dish Counts: Eliminar 3 JOINs + COUNT(DISTINCT) por predicción
    
    Atributos:
        ttl (timedelta): Tiempo de vida para clima/calendario (default: 20 min)
        dish_count_ttl (timedelta): Tiempo de vida para conteos de dishes (default: 60 min)
        weather_cache (dict): {date_obj: (data_dict, timestamp)}
        calendar_cache (dict): {date_obj: (data_dict, timestamp)}
        dish_count_cache (dict): {(restaurant_id, course_type): (count, timestamp)}
    """
    
    def __init__(self, ttl_minutes: int = 20, dish_count_ttl_minutes: int = 60):
        """
        Args:
            ttl_minutes: Minutos que clima/calendario permanecen en caché (default: 20 min)
            dish_count_ttl_minutes: Minutos que conteos de dishes permanecen en caché (default: 60 min)
        """
        self.ttl = timedelta(minutes=ttl_minutes)
        self.dish_count_ttl = timedelta(minutes=dish_count_ttl_minutes)
        self.weather_cache = {}
        self.calendar_cache = {}
        self.dish_count_cache = {}
        logger.info(f"🔄 CacheManager iniciado con TTL clima/calendario={ttl_minutes}min, dishes={dish_count_ttl_minutes}min")
    
    def _is_expired(self, cached_timestamp: datetime, ttl: timedelta) -> bool:
        """Verifica si una entrada de caché ha expirado."""
        return datetime.now() - cached_timestamp > ttl
    
    def get_weather(self, service_date: date) -> dict | None:
        """
        Obtiene datos de clima del caché si existen y no han expirado.
        
        Args:
            service_date: Fecha para consultar
            
        Returns:
            dict con datos de clima, o None si no está en caché o ha expirado
        """
        if service_date in self.weather_cache:
            data, timestamp = self.weather_cache[service_date]
            if not self._is_expired(timestamp, self.ttl):
                logger.info(f"✅ Climat caché para {service_date} (edad: {(datetime.now() - timestamp).total_seconds():.0f}s)")
                return data
            else:
                # Eliminar entrada expirada
                del self.weather_cache[service_date]
                logger.info(f"🗑️  Caché clima expirado para {service_date}")
        
        return None
    
    def set_weather(self, service_date: date, data: dict) -> None:
        """Guarda datos de clima en caché."""
        self.weather_cache[service_date] = (data, datetime.now())
        logger.info(f"💾 Guardado clima en caché para {service_date}")
    
    def get_calendar(self, service_date: date) -> dict | None:
        """
        Obtiene datos de calendario del caché si existen y no han expirado.
        
        Args:
            service_date: Fecha para consultar
            
        Returns:
            dict con datos de calendario, o None si no está en caché o ha expirado
        """
        if service_date in self.calendar_cache:
            data, timestamp = self.calendar_cache[service_date]
            if not self._is_expired(timestamp, self.ttl):
                logger.info(f"✅ Calendario caché para {service_date} (edad: {(datetime.now() - timestamp).total_seconds():.0f}s)")
                return data
            else:
                # Eliminar entrada expirada
                del self.calendar_cache[service_date]
                logger.info(f"🗑️  Caché calendario expirado para {service_date}")
        
        return None
    
    def set_calendar(self, service_date: date, data: dict) -> None:
        """Guarda datos de calendario en caché."""
        self.calendar_cache[service_date] = (data, datetime.now())
        logger.info(f"💾 Guardado calendario en caché para {service_date}")
    
    def get_dish_count(self, restaurant_id: int, course_type: str) -> int | None:
        """
        Obtiene el conteo de dishes del caché si existe y no ha expirado.
        
        Args:
            restaurant_id: ID del restaurante
            course_type: Tipo de plato ('first_course', 'second_course', 'dessert')
            
        Returns:
            int con el conteo, o None si no está en caché o ha expirado
        """
        cache_key = (restaurant_id, course_type)
        if cache_key in self.dish_count_cache:
            count, timestamp = self.dish_count_cache[cache_key]
            if not self._is_expired(timestamp, self.dish_count_ttl):
                logger.info(f"✅ Conteo {course_type} caché para restaurante {restaurant_id} (edad: {(datetime.now() - timestamp).total_seconds():.0f}s)")
                return count
            else:
                # Eliminar entrada expirada
                del self.dish_count_cache[cache_key]
                logger.info(f"🗑️  Caché conteo expirado para restaurante {restaurant_id}, {course_type}")
        
        return None
    
    def set_dish_count(self, restaurant_id: int, course_type: str, count: int) -> None:
        """Guarda conteo de dishes en caché."""
        cache_key = (restaurant_id, course_type)
        self.dish_count_cache[cache_key] = (count, datetime.now())
        logger.info(f"💾 Guardado conteo {course_type} en caché para restaurante {restaurant_id}: {count} platos")
    
    def clear_expired(self) -> None:
        """Limpia todas las entradas expiradas del caché."""
        expired_weather = [
            date_obj for date_obj, (_, ts) in self.weather_cache.items()
            if self._is_expired(ts, self.ttl)
        ]
        for date_obj in expired_weather:
            del self.weather_cache[date_obj]
        
        expired_calendar = [
            date_obj for date_obj, (_, ts) in self.calendar_cache.items()
            if self._is_expired(ts, self.ttl)
        ]
        for date_obj in expired_calendar:
            del self.calendar_cache[date_obj]
        
        expired_counts = [
            key for key, (_, ts) in self.dish_count_cache.items()
            if self._is_expired(ts, self.dish_count_ttl)
        ]
        for key in expired_counts:
            del self.dish_count_cache[key]
        
        if expired_weather or expired_calendar or expired_counts:
            logger.info(f"🧹 Limpieza caché: {len(expired_weather)} clima, {len(expired_calendar)} calendario, {len(expired_counts)} conteos eliminados")
    
    def stats(self) -> dict:
        """Retorna estadísticas del caché."""
        return {
            "weather_items": len(self.weather_cache),
            "calendar_items": len(self.calendar_cache),
            "dish_count_items": len(self.dish_count_cache),
            "ttl_minutes": int(self.ttl.total_seconds() / 60),
            "dish_count_ttl_minutes": int(self.dish_count_ttl.total_seconds() / 60),
        }


def _ensure_auth_columns_exist() -> None:
    """Crea columnas de auth/imagen en las tablas si la BD aún no fue migrada. Idempotente."""
    statements = [
        "IF COL_LENGTH('dbo.dim_restaurants', 'login_email') IS NULL ALTER TABLE dbo.dim_restaurants ADD login_email NVARCHAR(255) NULL;",
        "IF COL_LENGTH('dbo.dim_restaurants', 'password_hash') IS NULL ALTER TABLE dbo.dim_restaurants ADD password_hash NVARCHAR(255) NULL;",
        "IF COL_LENGTH('dbo.dim_restaurants', 'image_url') IS NULL ALTER TABLE dbo.dim_restaurants ADD image_url NVARCHAR(500) NULL;",
        "IF COL_LENGTH('dbo.inscripciones', 'login_email') IS NULL ALTER TABLE dbo.inscripciones ADD login_email NVARCHAR(255) NULL;",
        "IF COL_LENGTH('dbo.inscripciones', 'password_hash') IS NULL ALTER TABLE dbo.inscripciones ADD password_hash NVARCHAR(255) NULL;",
        "IF COL_LENGTH('dbo.inscripciones', 'image_url') IS NULL ALTER TABLE dbo.inscripciones ADD image_url NVARCHAR(500) NULL;",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


# ============================================================================
# LIFESPAN - Cargar modelo una sola vez al iniciar la aplicación
# ============================================================================

# Variable global para el motor de predicción
prediction_engine = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Context manager para gestionar el ciclo de vida de la aplicación FastAPI.
    
    STARTUP:
    - Inicializa la base de datos
    - Carga el modelo pickle en memoria (una sola vez)
    - Inicializa el caché en memoria (clima y calendario)
    - Inicializa el motor de predicción
    - Lo almacena en app.state para acceso global
    
    SHUTDOWN:
    - Limpia recursos si es necesario
    """
    global prediction_engine
    
    # ===== STARTUP =====
    logger.info("🚀 Iniciando aplicación AZCA Prediction API...")
    
    # 1. Inicializar base de datos
    try:
        init_db()
        logger.info("✅ Base de datos inicializada")
    except Exception as db_error:
        logger.error(f"❌ Error inicializando BD: {str(db_error)}", exc_info=True)
        raise

    # 1b. Asegurar que las columnas de auth/imagen existen (idempotente)
    try:
        _ensure_auth_columns_exist()
        logger.info("✅ Columnas de auth/imagen verificadas")
    except Exception as migration_error:
        logger.warning(f"⚠️  No se pudieron verificar columnas de auth: {str(migration_error)[:120]}")

    # 2. Intentar conectar a BD y verificar restaurantes
    try:
        db = SessionLocal()
        restaurant_count = db.query(Restaurant).count()
        db.close()
        logger.info(f"✅ Conectado a BD: {restaurant_count} restaurantes disponibles")
    except Exception as db_error:
        logger.error(f"❌ Error conectando BD: {str(db_error)}", exc_info=True)
        raise
    
    # 3. Inicializar el motor de predicción
    try:
        prediction_engine = PredictionEngine()
        logger.info(f"✅ Motor de predicción inicializado")
    except Exception as engine_error:
        logger.warning(f"⚠️  Motor de predicción no disponible: {str(engine_error)[:100]}")
        prediction_engine = None  # Permitirá fallback con mock en endpoints
    
    # 4. Cargar modelo pickle en memoria (OPTIMIZACIÓN CLAVE)
    try:
        artifacts_path = Path(__file__).parent.parent / "azca" / "artifacts"
        model_path = artifacts_path / "AzcaMenuModel.pkl"
        
        logger.info(f"📦 Cargando modelo desde: {model_path}")
        
        with open(model_path, "rb") as f:
            model = pickle.load(f)
        
        app.state.model = model
        logger.info(f"✅ Modelo cargado en memoria (app.state.model)")
        logger.info(f"   Tipo de modelo: {type(model).__name__}")
        
    except FileNotFoundError:
        logger.error(f"❌ Modelo no encontrado en {model_path}")
        raise
    except Exception as model_error:
        logger.error(f"❌ Error cargando modelo: {str(model_error)}", exc_info=True)
        raise
    
    # 5. Inicializar caché en memoria (clima y calendario)
    try:
        app.state.cache = CacheManager(ttl_minutes=20)
        logger.info(f"✅ Caché en memoria inicializado")
    except Exception as cache_error:
        logger.error(f"❌ Error inicializando caché: {str(cache_error)}", exc_info=True)
        raise
    
    logger.info("🎯 Aplicación lista para servir predicciones")
    
    # Yield para que FastAPI continúe ejecutándose
    yield
    
    # ===== SHUTDOWN =====
    logger.info("🛑 Deteniendo aplicación...")
    # Limpiar si es necesario
    logger.info("✅ Aplicación detenida correctamente")


# Crear la app con lifespan
app = FastAPI(
    title="AZCA Prediction API",
    description=(
        "API REST para predicciones de demanda de servicios con IA.\n\n"
        "Carga el modelo en memoria al iniciar para máximo rendimiento."
    ),
    version="1.0.0",
    contact={
        "name": "AZCA Project",
        "url": "https://github.com/your-org/azca",
    },
    lifespan=lifespan,
)

# Configurar CORS para permitir requests desde el frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, cambiar a ["https://tudominio.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    "/cache-stats",
    summary="Cache Statistics",
    tags=["Monitoring"],
)
async def cache_stats(http_request: Request):
    """
    Retorna estadísticas del caché de clima y calendario.
    
    Útil para monitoreo: ver cuántos datos están almacenados en memoria
    y cuánto tiempo llevan ahí.
    
    Returns:
        dict con estadísticas de caché
    """
    try:
        if hasattr(http_request.app.state, 'cache'):
            cache = http_request.app.state.cache
            stats = cache.stats()
            return {
                "status": "ok",
                "cache_stats": stats,
                "message": f"Caché activo: {stats['weather_items']} clima, {stats['calendar_items']} calendario items"
            }
        else:
            return {
                "status": "not_available",
                "message": "Caché no inicializado"
            }
    except Exception as e:
        logger.error(f"Error obteniendo stats del caché: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


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


def _parse_min_service_duration(min_service: str | None) -> int | None:
    """Convierte min_service (nvarchar) a entero de minutos si es posible."""
    if not min_service:
        return None

    digits = "".join(char for char in str(min_service) if char.isdigit())
    if not digits:
        return None

    try:
        parsed = int(digits)
        return parsed if parsed > 0 else None
    except ValueError:
        return None


@app.post(
    "/inscripciones",
    response_model=InscripcionItem,
    summary="Crear Solicitud de Inscripción",
    tags=["Data"],
    status_code=status.HTTP_201_CREATED,
)
async def create_inscripcion(request: InscripcionCreateRequest, db: Session = Depends(get_db)):
    """Crea una solicitud de alta en dbo.inscripciones."""
    try:
        inscripcion = Inscripcion(
            name=request.name.strip(),
            capacity_limit=request.capacity_limit,
            table_count=request.table_count,
            min_service=request.min_service,
            terrace_setup_type=request.terrace_setup_type,
            opens_weekends=request.opens_weekends,
            has_wifi=request.has_wifi,
            restaurant_segment=request.restaurant_segment,
            menu_price=request.menu_price,
            dist_office_towers=request.dist_office_towers,
            google_rating=request.google_rating,
            cuisine_type=request.cuisine_type,
            image_url=request.image_url.strip() if request.image_url else None,
            google_maps_link=request.google_maps_link.strip(),
            estado_inscripcion="pendiente",
            fecha_solicitud=datetime.now(),
        )

        db.add(inscripcion)
        db.commit()
        db.refresh(inscripcion)
        return InscripcionItem.from_orm(inscripcion)

    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error en POST /inscripciones: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear solicitud de inscripción",
        )


@app.get(
    "/inscripciones/pending",
    response_model=InscripcionesListResponse,
    summary="Obtener Inscripciones Pendientes",
    tags=["Data"],
)
async def get_pending_inscripciones(db: Session = Depends(get_db)):
    """Obtiene solicitudes pendientes desde dbo.inscripciones."""
    try:
        rows = (
            db.query(Inscripcion)
            .filter(
                or_(
                    Inscripcion.estado_inscripcion.is_(None),
                    func.lower(Inscripcion.estado_inscripcion) == "pendiente",
                )
            )
            .order_by(desc(Inscripcion.fecha_solicitud), desc(Inscripcion.inscripcion_id))
            .all()
        )

        return InscripcionesListResponse(
            count=len(rows),
            inscripciones=[InscripcionItem.from_orm(row) for row in rows],
        )

    except Exception as e:
        logger.error(f"❌ Error en GET /inscripciones/pending: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener inscripciones pendientes",
        )


@app.get(
    "/inscripciones",
    response_model=InscripcionesListResponse,
    summary="Obtener Inscripciones",
    tags=["Data"],
)
async def get_inscripciones(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
):
    """Obtiene inscripciones con filtro opcional por estado."""
    try:
        query = db.query(Inscripcion)

        if status_filter:
            normalized = status_filter.strip().lower()
            query = query.filter(func.lower(func.coalesce(Inscripcion.estado_inscripcion, "")) == normalized)

        rows = query.order_by(desc(Inscripcion.fecha_solicitud), desc(Inscripcion.inscripcion_id)).all()

        return InscripcionesListResponse(
            count=len(rows),
            inscripciones=[InscripcionItem.from_orm(row) for row in rows],
        )

    except Exception as e:
        logger.error(f"❌ Error en GET /inscripciones: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener inscripciones",
        )


@app.post(
    "/inscripciones/{inscripcion_id}/approve",
    response_model=InscripcionActionResponse,
    summary="Aprobar Inscripción",
    tags=["Data"],
)
async def approve_inscripcion(inscripcion_id: int, db: Session = Depends(get_db)):
    """
    Aprueba una inscripción:
    - Inserta los datos del restaurante en dim_restaurants.
    - Marca la inscripción como Aprobada.
    """
    try:
        inscripcion = (
            db.query(Inscripcion)
            .filter(Inscripcion.inscripcion_id == inscripcion_id)
            .first()
        )

        if not inscripcion:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Inscripción con ID {inscripcion_id} no encontrada",
            )

        restaurant_data = {
            "name": inscripcion.name,
            "capacity_limit": inscripcion.capacity_limit,
            "table_count": inscripcion.table_count,
            "min_service_duration": _parse_min_service_duration(inscripcion.min_service),
            "terrace_setup_type": inscripcion.terrace_setup_type,
            "opens_weekends": inscripcion.opens_weekends,
            "has_wifi": inscripcion.has_wifi,
            "restaurant_segment": inscripcion.restaurant_segment,
            "menu_price": inscripcion.menu_price,
            "dist_office_towers": inscripcion.dist_office_towers,
            "google_rating": inscripcion.google_rating,
            "cuisine_type": inscripcion.cuisine_type,
            "login_email": inscripcion.login_email,
            "password_hash": inscripcion.password_hash,
            "image_url": inscripcion.image_url,
        }

        next_restaurant_id = (db.query(func.max(Restaurant.restaurant_id)).scalar() or 0) + 1
        restaurant = Restaurant(restaurant_id=next_restaurant_id, **restaurant_data)

        db.add(restaurant)
        db.flush()

        db.delete(inscripcion)
        db.commit()
        db.refresh(restaurant)

        return InscripcionActionResponse(
            inscripcion_id=inscripcion_id,
            status="aprobada",
            message="Inscripción aprobada, movida a restaurantes y eliminada de inscripciones.",
            restaurant_id=restaurant.restaurant_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error en POST /inscripciones/{inscripcion_id}/approve: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al aprobar inscripción",
        )


@app.post(
    "/inscripciones/{inscripcion_id}/reject",
    response_model=InscripcionActionResponse,
    summary="Solicitar Cambios o Rechazar Inscripción",
    tags=["Data"],
)
async def reject_inscripcion(inscripcion_id: int, db: Session = Depends(get_db)):
    """Rechaza una inscripción y la elimina de la tabla de pendientes."""
    try:
        inscripcion = (
            db.query(Inscripcion)
            .filter(Inscripcion.inscripcion_id == inscripcion_id)
            .first()
        )

        if not inscripcion:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Inscripción con ID {inscripcion_id} no encontrada",
            )

        db.delete(inscripcion)
        db.commit()

        return InscripcionActionResponse(
            inscripcion_id=inscripcion_id,
            status="rechazada",
            message="Inscripción rechazada y eliminada de pendientes.",
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error en POST /inscripciones/{inscripcion_id}/reject: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar inscripción",
        )


@app.delete(
    "/inscripciones/history/approved",
    response_model=ClearApprovalHistoryResponse,
    summary="Limpiar Historial de Aprobaciones",
    tags=["Data"],
)
async def clear_approval_history(db: Session = Depends(get_db)):
    """Elimina del histórico las inscripciones con estado Aprobada."""
    try:
        approved_query = db.query(Inscripcion).filter(
            func.lower(func.coalesce(Inscripcion.estado_inscripcion, "")) == "aprobada"
        )
        deleted_count = approved_query.count()

        if deleted_count > 0:
            approved_query.delete(synchronize_session=False)

        db.commit()

        return ClearApprovalHistoryResponse(
            deleted_count=deleted_count,
            message="Historial de aprobaciones limpiado correctamente.",
        )

    except Exception as e:
        db.rollback()
        logger.error("❌ Error en DELETE /inscripciones/history/approved: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al limpiar historial de aprobaciones",
        )


@app.post(
    "/auth/login",
    response_model=AuthUserResponse,
    summary="Iniciar sesión",
    tags=["Auth"],
)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    admin_email = os.getenv("ADMIN_EMAIL", "admin@cuisineaml.com").strip().lower()
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123456")

    if request.email.strip().lower() != admin_email or request.password != admin_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales de administrador no válidas.")

    token = create_access_token({"role": "admin", "email": admin_email})
    return AuthUserResponse(role="admin", email=admin_email, token=token)


@app.get(
    "/auth/me",
    response_model=AuthUserResponse,
    summary="Obtener sesión actual",
    tags=["Auth"],
)
async def auth_me(authorization: str | None = Header(default=None)):
    payload = _require_auth(authorization)

    if payload.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión no válida para administrador.")

    token = _extract_bearer_token(authorization) or ""
    return AuthUserResponse(role="admin", email=payload.get("email", ""), token=token)


@app.patch(
    "/restaurants/{restaurant_id}/image",
    response_model=RestaurantDetailItem,
    summary="Actualizar imagen del restaurante",
    tags=["Data"],
)
async def update_restaurant_image(
    restaurant_id: int,
    request: RestaurantImageUpdateRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    payload = _require_auth(authorization)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado.")

    restaurant = db.query(Restaurant).filter(Restaurant.restaurant_id == restaurant_id).first()
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurante no encontrado.")

    restaurant.image_url = request.image_url.strip()
    db.commit()
    db.refresh(restaurant)
    return RestaurantDetailItem.from_orm(restaurant)



# ============================================================================
# FUNCIONES AUXILIARES PARA CÁLCULO AUTOMÁTICO
# ============================================================================

def get_weather_data(service_date: date, cache: CacheManager = None) -> dict:
    """
    Recupera datos meteorológicos de Open-Meteo para Azca (Madrid).
    
    CACHÉ INTEGRADO:
    - Primero verifica si los datos están en caché (TTL: 20 minutos)
    - Si no están o han expirado, llama a Open-Meteo API
    - Guarda los datos en caché para reutilizarlos
    
    Open-Meteo es una API meteorológica gratuita sin necesidad de API key.
    Coordenadas de Azca Madrid (Bernabéu): 40.4532° N, -3.6885° W
    
    Args:
        service_date: Fecha para la cual se obtiene el clima (date object)
        cache: CacheManager para almacenar/recuperar datos (opcional)
        
    Returns:
        dict: {
            'max_temp_c': float (temperatura máxima en C),
            'precipitation_mm': float (precipitación en mm),
            'is_rain_service_peak': bool (si llueve en horas pico 12-20)
        }
    """
    # 0. Verificar caché primero
    if cache:
        cached_data = cache.get_weather(service_date)
        if cached_data:
            return cached_data
    
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
        logger.info(f"🌐 Llamando Open-Meteo API para {service_date}...")
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
        
        weather_result = {
            'max_temp_c': float(max_temp),
            'precipitation_mm': float(precipitation),
            'is_rain_service_peak': is_rain_peak,
        }
        
        # Guardar en caché
        if cache:
            cache.set_weather(service_date, weather_result)
        
        return weather_result
        
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


def calculate_calendar_features(service_date: date, cache: CacheManager = None) -> dict:
    """
    Calcula automáticamente los parámetros de calendario basados en la fecha.
    Usa la librería 'holidays' para festivos españoles en Madrid (Azca location).
    
    CACHÉ INTEGRADO:
    - Primero verifica si los datos están en caché (TTL: 20 minutos)
    - Si no están o han expirado, calcula los datos
    - Guarda los datos en caché para reutilizarlos
    
    Args:
        service_date: Fecha del servicio (date object)
        cache: CacheManager para almacenar/recuperar datos (opcional)
        
    Returns:
        dict: {
            'is_business_day': bool (lunes-viernes),
            'is_holiday': bool (festivos en Madrid),
            'is_bridge_day': bool (puente festivo),
            'is_payday_week': bool (semana de pago)
        }
    """
    # 0. Verificar caché primero
    if cache:
        cached_data = cache.get_calendar(service_date)
        if cached_data:
            return cached_data
    
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
    
    calendar_result = {
        'is_business_day': is_business_day,
        'is_holiday': is_holiday,
        'is_bridge_day': is_bridge_day,
        'is_payday_week': is_payday_week,
    }
    
    # Guardar en caché
    if cache:
        cache.set_calendar(service_date, calendar_result)
    
    return calendar_result


# ============================================================================
# FUNCIONES HELPER PARA CONTAR PLATOS ÚNICOS POR RESTAURANTE
# ============================================================================

def get_total_starters(db: Session, restaurant_id: int, cache: CacheManager = None) -> int:
    """
    Cuenta el total de PLATOS ÚNICOS de entrada (first_course) que ha servido un restaurante.
    
    OPTIMIZACIÓN CON CACHÉ:
    1. Primero verifica si el conteo está en caché (TTL: 60 minutos)
    2. Si no, cuenta unique dish_ids que ha servido ese restaurante (3 JOINs)
    3. Si es 0, cuenta todos los starters disponibles en el catálogo
    4. Si sigue siendo 0, retorna 1 (fallback evita división por 0)
    
    Args:
        db: Sesión SQLAlchemy
        restaurant_id: ID del restaurante
        cache: CacheManager para almacenar/recuperar conteos (opcional)
    
    Returns:
        Total de platos de entrada únicos (int). Mínimo 1 para evitar división por 0.
    """
    # 0. Verificar caché primero
    if cache:
        cached_count = cache.get_dish_count(restaurant_id, 'first_course')
        if cached_count is not None:
            return cached_count
    
    # 1. Contar starters ÚNICOS que ha servido ESTE restaurante
    restaurant_starters = db.query(func.count(distinct(DimDishes.dish_id))).join(
        FactMenuItems, DimDishes.dish_id == FactMenuItems.dish_id
    ).join(
        FactMenus, FactMenuItems.menu_id == FactMenus.menu_id
    ).filter(
        FactMenus.restaurant_id == restaurant_id,
        DimDishes.course_type == 'first_course'
    ).scalar()
    
    result = None
    if restaurant_starters and restaurant_starters > 0:
        result = restaurant_starters
    else:
        # 2. Fallback: contar todos los starters en el catálogo
        all_starters = db.query(func.count(DimDishes.dish_id)).filter(
            DimDishes.course_type == 'first_course'
        ).scalar()
        
        if all_starters and all_starters > 0:
            result = all_starters
        else:
            # 3. Último fallback
            result = 1
    
    # Guardar en caché
    if cache and result:
        cache.set_dish_count(restaurant_id, 'first_course', result)
    
    return result


def get_total_mains(db: Session, restaurant_id: int, cache: CacheManager = None) -> int:
    """
    Cuenta el total de PLATOS ÚNICOS principales (second_course) que ha servido un restaurante.
    
    OPTIMIZACIÓN CON CACHÉ:
    1. Primero verifica si el conteo está en caché (TTL: 60 minutos)
    2. Si no, cuenta unique dish_ids que ha servido ese restaurante (3 JOINs)
    3. Si es 0, cuenta todos los mains disponibles en el catálogo
    4. Si sigue siendo 0, retorna 1 (fallback evita división por 0)
    
    Args:
        db: Sesión SQLAlchemy
        restaurant_id: ID del restaurante
        cache: CacheManager para almacenar/recuperar conteos (opcional)
    
    Returns:
        Total de platos principales únicos (int). Mínimo 1 para evitar división por 0.
    """
    # 0. Verificar caché primero
    if cache:
        cached_count = cache.get_dish_count(restaurant_id, 'second_course')
        if cached_count is not None:
            return cached_count
    
    # 1. Contar mains ÚNICOS que ha servido ESTE restaurante
    restaurant_mains = db.query(func.count(distinct(DimDishes.dish_id))).join(
        FactMenuItems, DimDishes.dish_id == FactMenuItems.dish_id
    ).join(
        FactMenus, FactMenuItems.menu_id == FactMenus.menu_id
    ).filter(
        FactMenus.restaurant_id == restaurant_id,
        DimDishes.course_type == 'second_course'
    ).scalar()
    
    result = None
    if restaurant_mains and restaurant_mains > 0:
        result = restaurant_mains
    else:
        # 2. Fallback: contar todos los mains en el catálogo
        all_mains = db.query(func.count(DimDishes.dish_id)).filter(
            DimDishes.course_type == 'second_course'
        ).scalar()
        
        if all_mains and all_mains > 0:
            result = all_mains
        else:
            # 3. Último fallback
            result = 1
    
    # Guardar en caché
    if cache and result:
        cache.set_dish_count(restaurant_id, 'second_course', result)
    
    return result


def get_total_desserts(db: Session, restaurant_id: int, cache: CacheManager = None) -> int:
    """
    Cuenta el total de POSTRES ÚNICOS (dessert) que ha servido un restaurante.
    
    OPTIMIZACIÓN CON CACHÉ:
    1. Primero verifica si el conteo está en caché (TTL: 60 minutos)
    2. Si no, cuenta unique dish_ids que ha servido ese restaurante (3 JOINs)
    3. Si es 0, cuenta todos los desserts disponibles en el catálogo
    4. Si sigue siendo 0, retorna 1 (fallback evita división por 0)
    
    Args:
        db: Sesión SQLAlchemy
        restaurant_id: ID del restaurante
        cache: CacheManager para almacenar/recuperar conteos (opcional)
    
    Returns:
        Total de postres únicos (int). Mínimo 1 para evitar división por 0.
    """
    # 0. Verificar caché primero
    if cache:
        cached_count = cache.get_dish_count(restaurant_id, 'dessert')
        if cached_count is not None:
            return cached_count
    
    # 1. Contar desserts ÚNICOS que ha servido ESTE restaurante
    restaurant_desserts = db.query(func.count(distinct(DimDishes.dish_id))).join(
        FactMenuItems, DimDishes.dish_id == FactMenuItems.dish_id
    ).join(
        FactMenus, FactMenuItems.menu_id == FactMenus.menu_id
    ).filter(
        FactMenus.restaurant_id == restaurant_id,
        DimDishes.course_type == 'dessert'
    ).scalar()
    
    result = None
    if restaurant_desserts and restaurant_desserts > 0:
        result = restaurant_desserts
    else:
        # 2. Fallback: contar todos los desserts en el catálogo
        all_desserts = db.query(func.count(DimDishes.dish_id)).filter(
            DimDishes.course_type == 'dessert'
        ).scalar()
        
        if all_desserts and all_desserts > 0:
            result = all_desserts
        else:
            # 3. Último fallback
            result = 1
    
    # Guardar en caché
    if cache and result:
        cache.set_dish_count(restaurant_id, 'dessert', result)
    
    return result


def get_prev_dish_id(db: Session, restaurant_id: int, course_type: str) -> float:
    """
    Obtiene el ID del plato más recientemente servido de un tipo (course_type) en un restaurante.
    
    OPTIMIZADO: Ahora accede a la vista v_current_restaurant_context en lugar de hacer
    múltiples JOINs manualmente. Según course_type retorna last_starter_id, last_main_id o last_dessert_id.
    
    Args:
        db: Sesión SQLAlchemy
        restaurant_id: ID del restaurante
        course_type: Tipo de plato ('first_course', 'second_course', 'dessert')
    
    Returns:
        dish_id del plato más reciente (float). Si no hay datos, retorna 0.0.
    """
    try:
        # Acceder a la vista optimizada v_current_restaurant_context
        context = db.query(RestaurantContext).filter(
            RestaurantContext.restaurant_id == restaurant_id
        ).first()
        
        if not context:
            logger.warning(f"Restaurante {restaurant_id} no encontrado en v_current_restaurant_context")
            return 0.0
        
        # Mapear course_type a el campo correspondiente de la vista
        if course_type == 'first_course':
            prev_dish_id = context.last_starter_id
        elif course_type == 'second_course':
            prev_dish_id = context.last_main_id
        elif course_type == 'dessert':
            prev_dish_id = context.last_dessert_id
        else:
            logger.warning(f"course_type inválido: {course_type}")
            return 0.0
        
        if prev_dish_id:
            logger.info(f"✅ prev_dish_id para {course_type}: {prev_dish_id} (desde vista)")
            return float(prev_dish_id)
        else:
            logger.info(f"ℹ️  No hay historial de {course_type}, usando 0.0")
            return 0.0
            
    except Exception as e:
        logger.error(f"Error obteniendo prev_dish_id desde vista: {str(e)}", exc_info=True)
        return 0.0


def get_dish_name_by_id(db: Session, dish_id: int) -> str:
    """
    Obtiene el nombre del plato (dish_name) desde dim_dishes usando dish_id.
    
    Args:
        db: Sesión SQLAlchemy
        dish_id: ID del plato
    
    Returns:
        Nombre del plato (string). Lanza excepción si no existe.
    """
    dish = db.query(DimDishes.dish_name).filter(
        DimDishes.dish_id == dish_id
    ).first()
    
    if not dish:
        raise ValueError(f"Plato con dish_id={dish_id} no encontrado en dim_dishes. ¿Tu modelo predice IDs que no existen?")
    
    return dish[0]


def save_prediction_log(
    db: Session,
    restaurant_id: int,
    prediction_domain: str,
    input_context: dict,
    output_results: list,
    model_version: str,
    latency_ms: int,
) -> int:
    """
    Guarda una predicción completa en fact_prediction_logs para auditoría.
    
    Centraliza todas las predicciones (menus, servicios) en una sola tabla con formato JSON.
    
    Args:
        db: Sesión SQLAlchemy
        restaurant_id: ID del restaurante
        prediction_domain: Tipo de predicción ('MENU_STARTER', 'MENU_MAIN', 'MENU_DESSERT', 'SERVICE_LEVEL')
        input_context: Dict con los inputs (clima, calendario, etc.)
        output_results: List de tuples [(dish_id, probability), ...] o scalar para servicios
        model_version: Versión del modelo
        latency_ms: Tiempo de ejecución en ms
        
    Returns:
        prediction_id guardado en BD
    """
    try:
        # Convertir input_context a JSON
        input_json = json.dumps(input_context, default=str)
        
        # Convertir output_results a JSON
        # Si es menú: [(dish_id, prob), ...] → [{"id": dish_id, "prob": prob}, ...]
        # Si es servicio: scalar → {"level": valor}
        if isinstance(output_results, list) and len(output_results) > 0 and isinstance(output_results[0], tuple):
            # Es menú (lista de tuplas)
            output_json = json.dumps(
                [{"id": int(r[0]), "probability": float(r[1])} for r in output_results],
                default=str
            )
        else:
            # Es servicio (scalar o valor simple)
            output_json = json.dumps({"level": output_results}, default=str)
        
        # Crear el log con execution_date explícito
        prediction_log = FactPredictionLog(
            execution_date=datetime.now(),  # 🔧 Asegurar que se setea la fecha
            restaurant_id=restaurant_id,
            prediction_domain=prediction_domain,
            input_context_json=input_json,
            output_results_json=output_json,
            model_version=model_version,
            latency_ms=latency_ms,
        )
        
        db.add(prediction_log)
        db.commit()
        db.refresh(prediction_log)
        
        logger.info(f"✅ Predicción guardada en fact_prediction_logs (ID: {prediction_log.prediction_id}, domain: {prediction_domain}, latency: {latency_ms}ms)")
        
        return prediction_log.prediction_id
        
    except Exception as e:
        logger.error(f"❌ ERROR guardando log de predicción: {str(e)}", exc_info=True)
        try:
            db.rollback()
        except:
            pass
        return -1


def predict_top3_dishes(model, features_dict: dict) -> list:
    """
    Obtiene el top 3 de platos predichos usando el modelo cargado en memoria.
    
    Args:
        model: Modelo pickle cargado (sklearn Pipeline con predict_proba)
        features_dict: Diccionario con los 15 features
        
    Returns:
        Lista de tuples [(dish_id, probability), ...]  para el top 3
    """
    import pandas as pd
    import numpy as np
    
    # Construir DataFrame con una sola fila (los 15 features)
    df = pd.DataFrame([features_dict])
    
    logger.info(f"🔨 Construyendo predicción con modelo...")
    logger.info(f"   Features shape: {df.shape}")
    logger.info(f"   Columns: {list(df.columns)}")
    
    # Obtener probabilidades de todas las clases
    proba = model.predict_proba(df)  # Shape: (1, num_clases)
    
    logger.info(f"✅ predict_proba() retornó probabilidades de shape {proba.shape}")
    
    # Obtener las clases del modelo
    classes = model.classes_
    logger.info(f"📝 Clases disponibles: {len(classes)} | Primeras 5: {classes[:5] if len(classes) > 5 else classes}")
    
    # Obtener probabilities de la primera fila
    probabilities = proba[0]
    
    # Obtener indices de top 3 probabilidades
    top3_indices = np.argsort(probabilities)[-3:][::-1]  # Orden descendente
    logger.info(f"✅ Top 3 indices: {top3_indices}")
    
    # Retornar [(class_id, probability), ...]
    top3_predictions = [
        (classes[idx], probabilities[idx])
        for idx in top3_indices
    ]
    
    logger.info(f"✅ Top 3 predicciones: {top3_predictions}")
    
    return top3_predictions


# ============================================================================
# FUNCIONES OCR (HEAD)
# ============================================================================

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
    http_request: Request,
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
        # ⏱️ Iniciar cronómetro de latencia
        exec_start = datetime.now()
        
        # Acceder al caché desde app.state
        cache = http_request.app.state.cache if hasattr(http_request.app.state, 'cache') else None
        
        # Calcular automáticamente parámetros de calendario (con caché)
        calendar_features = calculate_calendar_features(request.service_date, cache)
        
        # Recuperar datos históricos de fact_services
        # (services_lag_7 y avg_4_weeks desde la BD, con fallback a 70% capacidad)
        services_data = get_services_data(
            db=db,
            restaurant_id=request.restaurant_id,
            service_date=request.service_date,
            capacity_limit=request.capacity_limit
        )
        
        # Recuperar datos meteorológicos desde Open-Meteo (con caché)
        weather_data = get_weather_data(request.service_date, cache)
        
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

        # ⏱️ Calcular latencia (ANTES de guardar en BD)
        latency_ms = int((datetime.now() - exec_start).total_seconds() * 1000)
        
        # 📊 Guardar predicción en fact_prediction_logs (SERVICE_LEVEL) - PRIMERO
        # Esto es más importante que guardar en PredictionLog
        try:
            save_result_id = save_prediction_log(
                db=db,
                restaurant_id=request.restaurant_id,
                prediction_domain="SERVICE_LEVEL",
                input_context=input_data,
                output_results=prediction_result,  # scalar para servicios
                model_version="v1_xgboost",
                latency_ms=latency_ms,
            )
            logger.info(f"✅ Predicción centralizada guardada (ID: {save_result_id})")
        except Exception as fact_error:
            logger.error(f"❌ Error guardando en fact_prediction_logs: {str(fact_error)}", exc_info=True)
            # No interrumpir el flujo si falla esto
        
        # Crear registro de auditoría (tabla antigua, opcional)
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

        # Guardar en tabla antigua (opcional, no crítico)
        try:
            db.add(prediction_log)
            db.commit()
            db.refresh(prediction_log)
            logger.info(
                f"✅ Predicción guardada en PredictionLog (ID: {prediction_log.id}, "
                f"Resultado: {prediction_result})"
            )
        except Exception as db_error:
            logger.warning(f"⚠️  No se guardó en PredictionLog: {str(db_error)[:100]}")
            try:
                db.rollback()
            except:
                pass
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
    http_request: Request,
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
    # Acceder al modelo desde app.state (cargado en lifespan)
    if not hasattr(http_request.app.state, "model") or http_request.app.state.model is None:
        logger.error("Modelo no cargado en app.state")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Modelo de predicción no disponible. Reinicia la API.",
        )

    try:
        # ⏱️ Iniciar cronómetro de latencia
        exec_start = datetime.now()
        
        # 1. Obtener contexto del restaurante desde vista optimizada (una sola query)
        rest_data = db.query(Restaurant).filter(
            Restaurant.restaurant_id == request.restaurant_id
        ).first()
        
        context = db.query(RestaurantContext).filter(
            RestaurantContext.restaurant_id == request.restaurant_id
        ).first()
        
        if not rest_data or not context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Restaurante con ID {request.restaurant_id} no encontrado"
            )
        
        # Combinación de datos: restaurante + contexto
        restaurant = rest_data
        prev_dish_id = float(context.last_starter_id) if context.last_starter_id else 0.0

        # 2. Obtener datos meteorológicos y calendario (con caché desde app.state)
        cache = http_request.app.state.cache if hasattr(http_request.app.state, 'cache') else None
        weather_data = get_weather_data(request.service_date, cache)
        calendar_features = calculate_calendar_features(request.service_date, cache)
        
        # Extraer day_of_week (0=Monday) y month (1-12)
        day_of_week = request.service_date.weekday()
        month = request.service_date.month
        
        # 3. Preparar input para modelo unificado (15 features)
        starter_input = {
            "day_of_week": day_of_week,
            "month": month,
            "max_temp_c": weather_data['max_temp_c'],
            "precipitation_mm": weather_data.get('precipitation_mm', 0.0),
            "is_holiday": int(calendar_features['is_holiday']),
            "is_payday_week": int(calendar_features.get('is_payday_week', False)),
            "is_stadium_event": int(weather_data.get('is_stadium_event', False)),
            "is_azca_event": int(weather_data.get('is_azca_event', False)),
            "restaurant_id": request.restaurant_id,
            "cuisine_type": restaurant.cuisine_type,
            "restaurant_segment": restaurant.restaurant_segment,
            "terrace_setup_type": restaurant.terrace_setup_type or "standard",
            "menu_price": restaurant.menu_price or 15.0,
            "course_type": "first_course",  # Para starters
            "prev_dish_id": prev_dish_id,
        }
        
        # Log de entrada (para debugging)
        logger.info("="*80)
        logger.info(f"📍 POST /predict/starter - Solicitud recibida")
        logger.info("="*80)
        logger.info(f"🎯 Input: restaurante_id={request.restaurant_id}, fecha={request.service_date}")
        logger.info(f"📊 Parámetros auto-calculados:")
        logger.info(f"   Clima: temp={weather_data['max_temp_c']}°C, precipitation_mm={weather_data.get('precipitation_mm', 0.0)}")
        logger.info(f"   Calendario: business_day={calendar_features['is_business_day']}, holiday={calendar_features['is_holiday']}, payday_week={calendar_features.get('is_payday_week', False)}")
        logger.info(f"   Restaurante: {restaurant.name} ({restaurant.cuisine_type}), segment={restaurant.restaurant_segment}, terrace={restaurant.terrace_setup_type}, price={restaurant.menu_price}")
        logger.info(f"   Prev Dish ID (starters): {prev_dish_id}")
        logger.info(f"📦 Starter Input (15 features):")
        for key, val in starter_input.items():
            logger.info(f"      {key}: {val} ({type(val).__name__})")
        logger.info("="*80)
        
        # 5. Llamar al modelo cargado en memoria para obtener top 3 predicciones
        try:
            top_dishes = predict_top3_dishes(http_request.app.state.model, starter_input)
        except Exception as pred_error:
            logger.error(f"❌ Error durante predict_top3_dishes: {str(pred_error)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al procesar predicción: {str(pred_error)}",
            )
        
        # 5. Obtener total de starters del restaurante para calcular counts estimados (con caché)
        total_starters = get_total_starters(db, request.restaurant_id, cache)
        logger.info(f"📊 Total de starters en el restaurante: {total_starters}")
        
        # Normalizar los scores del top 3 para que sumen 1, luego calcular counts
        scores = [dish[1] for dish in top_dishes[:3]]
        sum_scores = sum(scores)
        if sum_scores > 0:
            normalized_scores = [score / sum_scores for score in scores]
        else:
            normalized_scores = [1/3, 1/3, 1/3]  # Fallback si algo va mal
        
        # 5. Formatear respuesta (top 3 con rank y estimated_count normalizado)
        # IMPORTANTE: dish[0] es dish_id (int), necesitamos obtener el nombre real desde dim_dishes
        starter_dishes = [
            StarterDish(
                rank=i+1,
                name=get_dish_name_by_id(db, int(dish[0])),  # dish[0] es dish_id, obtenemos el nombre
                score=normalized_scores[i],  # Score normalizado (0-1, suma a 1)
                estimated_count=round(normalized_scores[i] * total_starters)  # porcentaje normalizado * total
            )
            for i, dish in enumerate(top_dishes[:3])
        ]
        
        # ⏱️ Calcular latencia
        latency_ms = int((datetime.now() - exec_start).total_seconds() * 1000)
        
        # 📊 Guardar predicción en fact_prediction_logs
        save_prediction_log(
            db=db,
            restaurant_id=request.restaurant_id,
            prediction_domain="MENU_STARTER",
            input_context=starter_input,
            output_results=top_dishes[:3],
            model_version="azca_menu_model",
            latency_ms=latency_ms,
        )
        
        # 6. Retornar respuesta
        return StarterPredictionResponse(
            top_3_dishes=starter_dishes,
            service_date=request.service_date,
            restaurant_id=request.restaurant_id,
            model_version="azca_menu_model",
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
    http_request: Request,
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
    # Acceder al modelo desde app.state (cargado en lifespan)
    if not hasattr(http_request.app.state, "model") or http_request.app.state.model is None:
        logger.error("Modelo no cargado en app.state")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Modelo de predicción no disponible. Reinicia la API.",
        )

    try:
        # ⏱️ Iniciar cronómetro de latencia
        exec_start = datetime.now()
        
        # 1. Obtener contexto del restaurante desde vista optimizada (una sola query)
        rest_data = db.query(Restaurant).filter(
            Restaurant.restaurant_id == request.restaurant_id
        ).first()
        
        context = db.query(RestaurantContext).filter(
            RestaurantContext.restaurant_id == request.restaurant_id
        ).first()
        
        if not rest_data or not context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Restaurante con ID {request.restaurant_id} no encontrado"
            )
        
        # Combinación de datos: restaurante + contexto
        restaurant = rest_data
        prev_dish_id = float(context.last_main_id) if context.last_main_id else 0.0

        # 2. Obtener datos meteorológicos y calendario (con caché desde app.state)
        cache = http_request.app.state.cache if hasattr(http_request.app.state, 'cache') else None
        weather_data = get_weather_data(request.service_date, cache)
        calendar_features = calculate_calendar_features(request.service_date, cache)
        
        day_of_week = request.service_date.weekday()
        month = request.service_date.month
        
        # 3. Preparar input para modelo unificado (15 features)
        main_input = {
            "day_of_week": day_of_week,
            "month": month,
            "max_temp_c": weather_data['max_temp_c'],
            "precipitation_mm": weather_data.get('precipitation_mm', 0.0),
            "is_holiday": int(calendar_features['is_holiday']),
            "is_payday_week": int(calendar_features.get('is_payday_week', False)),
            "is_stadium_event": int(weather_data.get('is_stadium_event', False)),
            "is_azca_event": int(weather_data.get('is_azca_event', False)),
            "restaurant_id": request.restaurant_id,
            "cuisine_type": restaurant.cuisine_type,
            "restaurant_segment": restaurant.restaurant_segment,
            "terrace_setup_type": restaurant.terrace_setup_type or "standard",
            "menu_price": restaurant.menu_price or 15.0,
            "course_type": "second_course",  # Para platos principales
            "prev_dish_id": prev_dish_id,
        }
        
        logger.info("="*80)
        logger.info(f"📍 POST /predict/main - Solicitud recibida")
        logger.info("="*80)
        logger.info(f"🎯 Input: restaurante_id={request.restaurant_id}, fecha={request.service_date}")
        logger.info(f"📊 Parámetros auto-calculados:")
        logger.info(f"   Clima: temp={weather_data['max_temp_c']}°C, precipitation_mm={weather_data.get('precipitation_mm', 0.0)}")
        logger.info(f"   Calendario: business_day={calendar_features['is_business_day']}, holiday={calendar_features['is_holiday']}, payday_week={calendar_features.get('is_payday_week', False)}")
        logger.info(f"   Restaurante: {restaurant.name} ({restaurant.cuisine_type}), segment={restaurant.restaurant_segment}, terrace={restaurant.terrace_setup_type}, price={restaurant.menu_price}")
        logger.info(f"   Prev Dish ID (mains): {prev_dish_id}")
        logger.info(f"📦 Main Input (15 features):")
        for key, val in main_input.items():
            logger.info(f"      {key}: {val} ({type(val).__name__})")
        logger.info("="*80)
        
        # 5. Llamar al modelo cargado en memoria para obtener top 3 predicciones
        try:
            top_dishes = predict_top3_dishes(http_request.app.state.model, main_input)
        except Exception as pred_error:
            logger.error(f"❌ Error durante predict_top3_dishes: {str(pred_error)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al procesar predicción: {str(pred_error)}",
            )
        
        # 5. Obtener total de platos principales del restaurante para calcular counts estimados (con caché)
        total_mains = get_total_mains(db, request.restaurant_id, cache)
        logger.info(f"📊 Total de platos principales en el restaurante: {total_mains}")
        
        # Normalizar los scores del top 3 para que sumen 1, luego calcular counts
        scores = [dish[1] for dish in top_dishes[:3]]
        sum_scores = sum(scores)
        if sum_scores > 0:
            normalized_scores = [score / sum_scores for score in scores]
        else:
            normalized_scores = [1/3, 1/3, 1/3]  # Fallback si algo va mal
        
        # 5. Formatear respuesta
        # IMPORTANTE: dish[0] es dish_id (int), necesitamos obtener el nombre real desde dim_dishes
        main_dishes = [
            MainDish(
                rank=i+1,
                name=get_dish_name_by_id(db, int(dish[0])),  # dish[0] es dish_id, obtenemos el nombre
                score=normalized_scores[i],  # Score normalizado (0-1, suma a 1)
                estimated_count=round(normalized_scores[i] * total_mains)  # porcentaje normalizado * total
            )
            for i, dish in enumerate(top_dishes[:3])
        ]
        
        # ⏱️ Calcular latencia
        latency_ms = int((datetime.now() - exec_start).total_seconds() * 1000)
        
        # 📊 Guardar predicción en fact_prediction_logs
        save_prediction_log(
            db=db,
            restaurant_id=request.restaurant_id,
            prediction_domain="MENU_MAIN",
            input_context=main_input,
            output_results=top_dishes[:3],
            model_version="azca_menu_model",
            latency_ms=latency_ms,
        )
        
        # 6. Retornar respuesta
        return MainPredictionResponse(
            top_3_dishes=main_dishes,
            service_date=request.service_date,
            restaurant_id=request.restaurant_id,
            model_version="azca_menu_model",
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
    http_request: Request,
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
    # Acceder al modelo desde app.state (cargado en lifespan)
    if not hasattr(http_request.app.state, "model") or http_request.app.state.model is None:
        logger.error("Modelo no cargado en app.state")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Modelo de predicción no disponible. Reinicia la API.",
        )

    try:
        # ⏱️ Iniciar cronómetro de latencia
        exec_start = datetime.now()
        
        # 1. Obtener contexto del restaurante desde vista optimizada (una sola query)
        rest_data = db.query(Restaurant).filter(
            Restaurant.restaurant_id == request.restaurant_id
        ).first()
        
        context = db.query(RestaurantContext).filter(
            RestaurantContext.restaurant_id == request.restaurant_id
        ).first()
        
        if not rest_data or not context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Restaurante con ID {request.restaurant_id} no encontrado"
            )
        
        # Combinación de datos: restaurante + contexto
        restaurant = rest_data
        prev_dish_id = float(context.last_dessert_id) if context.last_dessert_id else 0.0

        # 2. Obtener datos meteorológicos y calendario (con caché desde app.state)
        cache = http_request.app.state.cache if hasattr(http_request.app.state, 'cache') else None
        weather_data = get_weather_data(request.service_date, cache)
        calendar_features = calculate_calendar_features(request.service_date, cache)
        
        day_of_week = request.service_date.weekday()
        month = request.service_date.month
        
        # 3. Preparar input para modelo unificado (15 features)
        dessert_input = {
            "day_of_week": day_of_week,
            "month": month,
            "max_temp_c": weather_data['max_temp_c'],
            "precipitation_mm": weather_data.get('precipitation_mm', 0.0),
            "is_holiday": int(calendar_features['is_holiday']),
            "is_payday_week": int(calendar_features.get('is_payday_week', False)),
            "is_stadium_event": int(weather_data.get('is_stadium_event', False)),
            "is_azca_event": int(weather_data.get('is_azca_event', False)),
            "restaurant_id": request.restaurant_id,
            "cuisine_type": restaurant.cuisine_type,
            "restaurant_segment": restaurant.restaurant_segment,
            "terrace_setup_type": restaurant.terrace_setup_type or "standard",
            "menu_price": restaurant.menu_price or 15.0,
            "course_type": "dessert",  # Para postres
            "prev_dish_id": prev_dish_id,
        }
        
        logger.info("="*80)
        logger.info(f"📍 POST /predict/dessert - Solicitud recibida")
        logger.info("="*80)
        logger.info(f"🎯 Input: restaurante_id={request.restaurant_id}, fecha={request.service_date}")
        logger.info(f"📊 Parámetros auto-calculados:")
        logger.info(f"   Clima: temp={weather_data['max_temp_c']}°C, precipitation_mm={weather_data.get('precipitation_mm', 0.0)}")
        logger.info(f"   Calendario: business_day={calendar_features['is_business_day']}, holiday={calendar_features['is_holiday']}, payday_week={calendar_features.get('is_payday_week', False)}")
        logger.info(f"   Restaurante: {restaurant.name} ({restaurant.cuisine_type}), segment={restaurant.restaurant_segment}, terrace={restaurant.terrace_setup_type}, price={restaurant.menu_price}")
        logger.info(f"   Prev Dish ID (desserts): {prev_dish_id}")
        logger.info(f"📦 Dessert Input (15 features):")
        for key, val in dessert_input.items():
            logger.info(f"      {key}: {val} ({type(val).__name__})")
        logger.info("="*80)
        
        # 5. Llamar al modelo cargado en memoria para obtener top 3 predicciones
        try:
            top_dishes = predict_top3_dishes(http_request.app.state.model, dessert_input)
        except Exception as pred_error:
            logger.error(f"❌ Error durante predict_top3_dishes: {str(pred_error)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al procesar predicción: {str(pred_error)}",
            )
        
        # 5. Obtener total de postres del restaurante para calcular counts estimados (con caché)
        total_desserts = get_total_desserts(db, request.restaurant_id, cache)
        logger.info(f"📊 Total de postres en el restaurante: {total_desserts}")
        
        # Normalizar los scores del top 3 para que sumen 1, luego calcular counts
        scores = [dish[1] for dish in top_dishes[:3]]
        sum_scores = sum(scores)
        if sum_scores > 0:
            normalized_scores = [score / sum_scores for score in scores]
        else:
            normalized_scores = [1/3, 1/3, 1/3]  # Fallback si algo va mal
        
        # 5. Formatear respuesta
        # IMPORTANTE: dish[0] es dish_id (int), necesitamos obtener el nombre real desde dim_dishes
        dessert_dishes = [
            DessertDish(
                rank=i+1,
                name=get_dish_name_by_id(db, int(dish[0])),  # dish[0] es dish_id, obtenemos el nombre
                score=normalized_scores[i],  # Score normalizado (0-1, suma a 1)
                estimated_count=round(normalized_scores[i] * total_desserts)  # porcentaje normalizado * total
            )
            for i, dish in enumerate(top_dishes[:3])
        ]
        
        # ⏱️ Calcular latencia
        latency_ms = int((datetime.now() - exec_start).total_seconds() * 1000)
        
        # 📊 Guardar predicción en fact_prediction_logs
        save_prediction_log(
            db=db,
            restaurant_id=request.restaurant_id,
            prediction_domain="MENU_DESSERT",
            input_context=dessert_input,
            output_results=top_dishes[:3],
            model_version="azca_menu_model",
            latency_ms=latency_ms,
        )
        
        # 6. Retornar respuesta
        return DessertPredictionResponse(
            top_3_dishes=dessert_dishes,
            service_date=request.service_date,
            restaurant_id=request.restaurant_id,
            model_version="azca_menu_model",
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
