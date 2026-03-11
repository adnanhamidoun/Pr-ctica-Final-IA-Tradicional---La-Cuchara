# Script PowerShell para ejecutar la API

Write-Host ""
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "  AZCA Prediction API - Startup" -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host ""

# Activar entorno virtual
Write-Host "📦 Activando entorno virtual..." -ForegroundColor Yellow
& ".\azca_310_env\Scripts\Activate.ps1"

# Instalar dependencias faltantes
Write-Host "⬇️  Instalando dependencias necesarias..." -ForegroundColor Yellow
pip install sqlalchemy python-dotenv --quiet

Write-Host ""
Write-Host "====================================================================" -ForegroundColor Green
Write-Host "  API iniciando..." -ForegroundColor Green
Write-Host "====================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "🌐 Servidor:   http://localhost:8000" -ForegroundColor Green
Write-Host "📚 Swagger:    http://localhost:8000/docs" -ForegroundColor Green
Write-Host "❤️  Health:     http://localhost:8000/health" -ForegroundColor Green
Write-Host ""
Write-Host "⏹️  Presiona Ctrl+C para detener" -ForegroundColor Yellow
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host ""

# Ejecutar la API
uvicorn azca.api.main:app --reload --host 0.0.0.0 --port 8000

Read-Host "Presiona Enter para cerrar"
