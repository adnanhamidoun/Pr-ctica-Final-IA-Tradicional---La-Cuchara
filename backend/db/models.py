"""
Definición de modelos ORM para la base de datos Azure SQL.

Este módulo define los modelos SQLAlchemy que mapean las tablas
de la base de datos. Actualmente contiene el modelo PredictionLog
que se utiliza para auditoría y re-entrenamiento de modelos de IA.

Classes:
    PredictionLog: Modelo para la tabla de auditoría de predicciones.
    FactServices: Modelo para la tabla de hechos con datos históricos.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, Float, DateTime, Date, Boolean, String, Text
from sqlalchemy.sql import func
from .database import Base


class Restaurant(Base):
    """
    Modelo ORM para la tabla dim_restaurants.
    
    Contiene toda la información de los restaurantes para predicción.
    """
    __tablename__ = "dim_restaurants"
    
    restaurant_id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    capacity_limit = Column(Integer, nullable=True)
    table_count = Column(Integer, nullable=True)
    min_service_duration = Column(Integer, nullable=True)
    terrace_setup_type = Column(String(100), nullable=True)
    opens_weekends = Column(Boolean, nullable=True)
    has_wifi = Column(Boolean, nullable=True)
    restaurant_segment = Column(String(100), nullable=True)
    menu_price = Column(Float, nullable=True)
    dist_office_towers = Column(Integer, nullable=True)
    google_rating = Column(Float, nullable=True)
    cuisine_type = Column(String(100), nullable=True)
    
    def __repr__(self):
        return f"<Restaurant(id={self.restaurant_id}, name='{self.name}')>"


class DimDish(Base):
    """
    Modelo ORM para la tabla dim_dishes.

    Almacena platos normalizados extraídos por OCR y su tipo de curso.
    """

    __tablename__ = "dim_dishes"

    dish_id = Column(Integer, primary_key=True, autoincrement=True)
    course_type = Column(String(50), nullable=False)
    dish_name = Column(String(500), nullable=False)

    def __repr__(self):
        return f"<DimDish(id={self.dish_id}, course_type='{self.course_type}', dish_name='{self.dish_name}')>"


class PredictionLog(Base):
    """
    Modelo ORM para la tabla PredictionLogs de auditoría.

    Esta tabla registra cada predicción realizada por el modelo de IA,
    incluyendo los parámetros de entrada, la predicción generada y
    metadatos relevantes. Se utiliza para:

    1. **Auditoría**: Mantener un historial completo de todas las predicciones.
    2. **Re-entrenamiento**: Recopilar datos de entrada y salida para
       validación de modelo y re-entrenamiento con nuevos datos históricos.
    3. **Debugging**: Facilitar la investigación de predicciones incorrectas.

    Attributes:
        id (int): Identificador único autoincrementado (BIGINT IDENTITY).
        execution_timestamp (datetime): Timestamp de cuándo se ejecutó la predicción.
            Por defecto, se asigna la fecha/hora actual del servidor.
        service_date (date): Fecha del día que se está prediciendo.
        max_temp_c (float): Temperatura máxima predicha en grados Celsius.
        precipitation_mm (float): Precipitación predicha en milímetros.
        is_stadium_event (bool): Indicador de si hay evento en estadio (match de fútbol).
        is_payday_week (bool): Indicador de si es semana de cobro/salario.
        prediction_result (int): Resultado de la predicción del modelo IA
            (ej: cantidad predicha de usuarios).
        model_version (str): Versión del modelo que realizó la predicción
            (ej: 'v1_xgboost', 'v2_lstm', etc.).
        full_input_json (str): JSON con el conjunto completo de inputs
            para reproducibilidad y auditoría.
    """

    __tablename__ = "PredictionLogs"

    # Campos de la tabla
    id = Column(Integer, primary_key=True, autoincrement=True)
    execution_timestamp = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        doc="Timestamp de ejecución de la predicción"
    )
    service_date = Column(
        Date,
        nullable=False,
        doc="Fecha del día que se está prediciendo"
    )
    max_temp_c = Column(
        Float,
        nullable=True,
        doc="Temperatura máxima en grados Celsius"
    )
    precipitation_mm = Column(
        Float,
        nullable=True,
        doc="Precipitación en milímetros"
    )
    is_stadium_event = Column(
        Boolean,
        nullable=True,
        doc="¿Hay evento en estadio?"
    )
    is_payday_week = Column(
        Boolean,
        nullable=True,
        doc="¿Es semana de cobro?"
    )
    prediction_result = Column(
        Integer,
        nullable=False,
        doc="Resultado de la predicción del modelo"
    )
    model_version = Column(
        String(50),
        nullable=True,
        default="v1_xgboost",
        doc="Versión del modelo utilizado"
    )
    full_input_json = Column(
        Text,
        nullable=True,
        doc="JSON con todos los inputs para reproducibilidad"
    )

    def __repr__(self):
        """Representación en string del objeto PredictionLog."""
        return (
            f"<PredictionLog("
            f"id={self.id}, "
            f"service_date={self.service_date}, "
            f"prediction_result={self.prediction_result}, "
            f"model_version={self.model_version})>"
        )

    def to_dict(self):
        """
        Convierte el registro a diccionario para serialización JSON.

        Returns:
            dict: Diccionario con los atributos del registro.
        """
        return {
            "id": self.id,
            "execution_timestamp": self.execution_timestamp.isoformat()
            if self.execution_timestamp else None,
            "service_date": self.service_date.isoformat()
            if self.service_date else None,
            "max_temp_c": self.max_temp_c,
            "precipitation_mm": self.precipitation_mm,
            "is_stadium_event": self.is_stadium_event,
            "is_payday_week": self.is_payday_week,
            "prediction_result": self.prediction_result,
            "model_version": self.model_version,
            "full_input_json": self.full_input_json,
        }


class FactServices(Base):
    """
    Modelo ORM para la tabla fact_services.
    
    Contiene datos históricos de servicios por restaurante y fecha.
    Se utiliza para recuperar valores lag (services_lag_7 y avg_4_weeks)
    para alimentar el modelo de predicción.
    
    Attributes:
        date_id: Identificador de fecha en formato YYYYMMDD (entero)
        restaurant_id: ID del restaurante
        services_lag_7: Número de servicios hace 7 días
        avg_4_weeks: Promedio de servicios últimas 4 semanas
    """
    __tablename__ = "fact_services"
    
    date_id = Column(Integer, primary_key=True)
    restaurant_id = Column(Integer, primary_key=True)
    services_lag_7 = Column(Float, nullable=True)
    avg_4_weeks = Column(Float, nullable=True)
    
    def __repr__(self):
        return f"<FactServices(date={self.date_id}, rest_id={self.restaurant_id}, lag7={self.services_lag_7}, avg4w={self.avg_4_weeks})>"


class MenusAzca(Base):
    """
    Modelo ORM para la tabla Menus_Azca.
    
    Contiene el historial de menús servidos en cada restaurante,
    incluyendo platos de entrada, plato principal y postre.
    Se utiliza para contar cuántos platos de cada tipo sirve cada restaurante.
    
    Attributes:
        restaurant_id: ID del restaurante
        first_course: Nombre del plato de entrada
        second_course: Nombre del plato principal
        dessert: Nombre del postre
    """
    __tablename__ = "Menus_Azca"
    
    restaurant_id = Column(Integer, primary_key=True, index=True)
    first_course = Column(String(255), primary_key=True, nullable=True)
    second_course = Column(String(255), nullable=True)
    dessert = Column(String(255), nullable=True)
    
    def __repr__(self):
        return f"<MenusAzca(rest_id={self.restaurant_id}, first='{self.first_course}', second='{self.second_course}', dessert='{self.dessert}')>"


class DimDishes(Base):
    """
    Modelo ORM para la tabla dim_dishes.
    
    Tabla de dimensión con información de todos los platos disponibles.
    """
    __tablename__ = "dim_dishes"
    
    dish_id = Column(Integer, primary_key=True)
    dish_name = Column(String(255), nullable=False)
    course_type = Column(String(50), nullable=False)  # 'first_course', 'second_course', 'dessert'
    
    def __repr__(self):
        return f"<DimDishes(id={self.dish_id}, name='{self.dish_name}', course='{self.course_type}')>"


class FactMenuItems(Base):
    """
    Modelo ORM para la tabla fact_menu_items.
    
    Tabla de hechos que vincula menús con platos específicos.
    """
    __tablename__ = "fact_menu_items"
    
    menu_id = Column(Integer, primary_key=True)
    dish_id = Column(Integer, primary_key=True)
    
    def __repr__(self):
        return f"<FactMenuItems(menu_id={self.menu_id}, dish_id={self.dish_id})>"


class FactMenus(Base):
    """
    Modelo ORM para la tabla fact_menus.
    
    Tabla de hechos con historial de menús servidos por restaurante y fecha.
    """
    __tablename__ = "fact_menus"
    
    menu_id = Column(Integer, primary_key=True)
    restaurant_id = Column(Integer, nullable=False, index=True)
    date_id = Column(Integer, nullable=False)  # YYYYMMDD format
    
    def __repr__(self):
        return f"<FactMenus(menu_id={self.menu_id}, rest_id={self.restaurant_id}, date={self.date_id})>"


class RestaurantContext(Base):
    """
    Modelo ORM para la vista v_current_restaurant_context.
    
    Vista optimizada que centraliza los datos del restaurante y los últimos platos
    servidos por tipo de curso. Evita múltiples JOINs en el código Python.
    
    Atributos:
        restaurant_id: ID del restaurante (PK)
        cuisine_type: Tipo de cocina
        restaurant_segment: Segmento del restaurante
        menu_price: Precio promedio del menú
        terrace_setup_type: Tipo de setup de terraza
        last_starter_id: ID del último plato de entrada servido (nullable)
        last_main_id: ID del último plato principal servido (nullable)
        last_dessert_id: ID del último postre servido (nullable)
    """
    __tablename__ = "v_current_restaurant_context"
    
    restaurant_id = Column(Integer, primary_key=True)
    cuisine_type = Column(String(100), nullable=True)
    restaurant_segment = Column(String(100), nullable=True)
    menu_price = Column(Float, nullable=True)
    terrace_setup_type = Column(String(100), nullable=True)
    last_starter_id = Column(Integer, nullable=True)
    last_main_id = Column(Integer, nullable=True)
    last_dessert_id = Column(Integer, nullable=True)
    
    def __repr__(self):
        return (
            f"<RestaurantContext(id={self.restaurant_id}, "
            f"cuisine={self.cuisine_type}, "
            f"last_starter={self.last_starter_id}, "
            f"last_main={self.last_main_id}, "
            f"last_dessert={self.last_dessert_id})>"
        )


class FactPredictionLog(Base):
    """
    Modelo ORM para la tabla fact_prediction_logs.
    
    Auditoría centralizada de TODAS las predicciones del sistema:
    - Predicciones de menús (MENU_STARTER, MENU_MAIN, MENU_DESSERT)
    - Predicciones de servicios (SERVICE_LEVEL)
    
    Permite rastrear qué inputs generaron qué outputs, comparar con datos reales,
    medir latency, y auditar el rendimiento del modelo.
    
    Atributos:
        prediction_id: ID único (auto-increment)
        execution_date: Timestamp de cuándo se ejecutó
        restaurant_id: ID del restaurante
        prediction_domain: Tipo de predicción ('MENU_STARTER', 'MENU_MAIN', 'MENU_DESSERT', 'SERVICE_LEVEL')
        input_context_json: JSON con los inputs (clima, calendario, restaurante, etc.)
        output_results_json: JSON con los resultados predichos (top 3 dishes o nivel de servicio)
        model_version: Versión del modelo usado
        latency_ms: Tiempo de ejecución en milisegundos
        actual_outcome_json: JSON con los datos reales (se llena después de servir)
    """
    __tablename__ = "fact_prediction_logs"
    
    prediction_id = Column(Integer, primary_key=True, autoincrement=True)
    execution_date = Column(DateTime, default=datetime.utcnow, nullable=True, index=True)  # Coincide con Azure (nullable=True)
    restaurant_id = Column(Integer, nullable=False, index=True)
    
    # Diferenciador: qué tipo de predicción es
    prediction_domain = Column(String(50), nullable=False, index=True)  
    
    # Contexto de entrada (NVARCHAR(MAX) → Text en SQLAlchemy)
    input_context_json = Column(Text, nullable=False)
    
    # Resultados de IA (NVARCHAR(MAX) → Text en SQLAlchemy)
    output_results_json = Column(Text, nullable=False)
    
    # Rendimiento
    model_version = Column(String(50), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    
    # Comparación vs realidad (NVARCHAR(MAX), nullable → Text, nullable)
    actual_outcome_json = Column(Text, nullable=True)
    
    def __repr__(self):
        return (
            f"<FactPredictionLog(id={self.prediction_id}, "
            f"rest_id={self.restaurant_id}, "
            f"domain={self.prediction_domain}, "
            f"latency={self.latency_ms}ms)>"
        )
