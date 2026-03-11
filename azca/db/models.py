"""
Definición de modelos ORM para la base de datos Azure SQL.

Este módulo define los modelos SQLAlchemy que mapean las tablas
de la base de datos. Actualmente contiene el modelo PredictionLog
que se utiliza para auditoría y re-entrenamiento de modelos de IA.

Classes:
    PredictionLog: Modelo para la tabla de auditoría de predicciones.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, Float, DateTime, Date, Boolean, String, Text
from sqlalchemy.sql import func
from azca.db.database import Base


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
