@echo off
REM Activar entorno virtual y ejecutar la API

echo.
echo ====================================================================
echo  AZCA Prediction API - Startup
echo ====================================================================
echo.

REM Activar entorno virtual
call azca_310_env\Scripts\activate.bat

REM Instalar dependencias faltantes
echo Instalando dependencias...
pip install sqlalchemy python-dotenv --quiet

REM Mostrar información
echo.
echo ====================================================================
echo  API iniciando...
echo ====================================================================
echo.
echo Servidor: http://localhost:8000
echo Swagger:  http://localhost:8000/docs
echo Health:   http://localhost:8000/health
echo.
echo Presiona Ctrl+C para detener
echo ====================================================================
echo.

REM Ejecutar la API
uvicorn azca.api.main:app --reload --host 0.0.0.0 --port 8000

pause
