"""
Módulo de configuración y modelos de base de datos.

Exporta los componentes principales para la integración con FastAPI.
"""

from .database import engine, SessionLocal, Base, get_db, init_db
from .models import (
    PredictionLog, 
    Restaurant, 
    FactServices, 
    MenusAzca, 
    DimDishes, 
    FactMenuItems, 
    FactMenus, 
    RestaurantContext, 
    FactPredictionLog
)

__all__ = [
    "engine",
    "SessionLocal",
    "Base",
    "get_db",
    "init_db",
    "PredictionLog",
    "Restaurant",
    "FactServices",
    "MenusAzca",
    "DimDishes",
    "FactMenuItems",
    "FactMenus",
    "RestaurantContext",
    "FactPredictionLog",
]
