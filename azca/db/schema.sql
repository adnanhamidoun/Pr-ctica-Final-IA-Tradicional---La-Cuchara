-- Creación de la tabla de auditoría de predicciones
CREATE TABLE PredictionLogs (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    execution_timestamp DATETIME2 DEFAULT GETDATE(), -- Cuándo se consultó
    service_date DATE NOT NULL,                      -- Día predicho
    max_temp_c FLOAT,                                -- Input: Temperatura
    precipitation_mm FLOAT,                          -- Input: Lluvia
    is_stadium_event BIT,                            -- Input: Fútbol
    is_payday_week BIT,                              -- Input: Cobro
    prediction_result INT NOT NULL,                  -- Resultado IA
    model_version VARCHAR(50) DEFAULT 'v1_xgboost',  -- Versión
    full_input_json NVARCHAR(MAX)                    -- Backup total
);

-- Índice para que la App cargue rápido el historial
CREATE INDEX idx_service_date ON PredictionLogs(service_date);