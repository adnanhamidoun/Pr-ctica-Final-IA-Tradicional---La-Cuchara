@echo off
REM Script para hacer commit de los cambios

echo.
echo ====================================================================
echo   AZCA - Git Commit
echo ====================================================================
echo.

git add -A

git commit -m "feat: Agregar API FastAPI con Azure SQL, database layer y modelos ORM

- azca/db/database.py: Configuracion SQLAlchemy con Azure SQL + fallback SQLite
- azca/db/models.py: Modelo ORM PredictionLog (auditoría de predicciones)
- azca/api/main.py: API FastAPI completa (250+ líneas)
  * GET /health (health check)
  * POST /predict (predicción + guardado en BD)
  * GET /docs (Swagger automático)
- azca/db/__init__.py: Exportaciones limpias
- azca/api/__init__.py: Exportaciones limpias
- .env.example: Plantilla de credenciales Azure SQL
- Documentación: PRUEBAS.md, PROJECT_SUMMARY.txt, COMPLETION_REPORT.txt

FEATURES IMPLEMENTADOS:
✅ Conexión segura a Azure SQL (urllib.parse.quote_plus)
✅ Variables de entorno para credenciales
✅ SessionLocal y dependency injection FastAPI
✅ ORM completo con SQLAlchemy
✅ Validación Pydantic (request/response)
✅ Swagger/OpenAPI documentation automática
✅ Logging detallado con timestamps
✅ Auditoría de predicciones en tabla PredictionLogs
✅ Manejo profesional de errores (422, 503, 500)
✅ Fallback a SQLite en-memoria para testing
✅ Fallback a predictor mock si PredictionEngine no disponible
✅ PEP8 compliance y docstrings

TESTING COMPLETADO:
✅ GET /health → 200 OK
✅ POST /predict → 201 CREATED
✅ Swagger docs → Disponible en /docs
✅ Validación de datos → Pydantic funciona
✅ BD SQLite funcional → Predicciones auditadas"

echo.
echo ====================================================================
echo   Commit completado!
echo ====================================================================
echo.

git log --oneline -1

pause
