# 🧪 Guía de Pruebas - AZCA Prediction API

## ✅ Checklist Rápido

- [x] `azca/db/database.py` creado (conexión Azure SQL + SQLAlchemy)
- [x] `azca/db/models.py` creado (modelo ORM PredictionLog)
- [x] `azca/api/main.py` creado (FastAPI con 2 endpoints)
- [x] `.env.example` creado (plantilla de credenciales)
- [x] `.env` configurado (credenciales reales)

---

## 🚀 FORMA MÁS RÁPIDA DE PROBAR

### 1️⃣ Abre PowerShell en la carpeta del proyecto:

```powershell
cd C:\Users\adnan\Desktop\Azca
```

### 2️⃣ Ejecuta el script de arranque:

```powershell
# Opción 1: Script PowerShell (recomendado)
.\run_api.ps1

# Opción 2: Comando directo
.\azca_310_env\Scripts\Activate.ps1
pip install sqlalchemy python-dotenv
uvicorn azca.api.main:app --reload
```

### 3️⃣ Verifica que la API esté viva:

Abre en el navegador:
```
http://localhost:8000/health
```

Deberías ver:
```json
{
  "status": "healthy",
  "message": "API y base de datos funcionando correctamente"
}
```

### 4️⃣ Abre la documentación interactiva:

```
http://localhost:8000/docs
```

---

## 🧪 PRUEBAS DETALLADAS

### Test 1: Health Check

**URL:** `GET http://localhost:8000/health`

**Con curl:**
```bash
curl http://localhost:8000/health
```

**Respuesta esperada:**
```json
{
  "status": "healthy",
  "message": "API y base de datos funcionando correctamente"
}
```

---

### Test 2: Realizar una Predicción

**URL:** `POST http://localhost:8000/predict`

**Con curl:**
```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "service_date": "2026-03-15",
    "max_temp_c": 28.5,
    "precipitation_mm": 0.0,
    "is_stadium_event": false,
    "is_payday_week": true
  }'
```

**O con PowerShell:**
```powershell
$body = @{
    service_date = "2026-03-15"
    max_temp_c = 28.5
    precipitation_mm = 0.0
    is_stadium_event = $false
    is_payday_week = $true
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/predict" `
  -Method POST `
  -Headers @{"Content-Type" = "application/json"} `
  -Body $body
```

**Respuesta esperada:**
```json
{
  "prediction_result": 150,
  "service_date": "2026-03-15",
  "model_version": "v1_xgboost",
  "execution_timestamp": "2026-03-11T10:30:00",
  "log_id": 1
}
```

---

### Test 3: Validación de Datos

**Datos inválidos (max_temp_c no es número):**

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "service_date": "2026-03-15",
    "max_temp_c": "no_es_numero",
    "precipitation_mm": 0.0,
    "is_stadium_event": false,
    "is_payday_week": true
  }'
```

**Respuesta esperada:**
```json
{
  "detail": [
    {
      "type": "float_parsing",
      "loc": ["body", "max_temp_c"],
      "msg": "Input should be a valid number"
    }
  ]
}
```

---

### Test 4: Ver la Documentación Swagger

Abre en el navegador:
```
http://localhost:8000/docs
```

Ahí puedes:
- ✅ Ver todos los endpoints
- ✅ Ver los esquemas Pydantic
- ✅ Probar endpoints directamente
- ✅ Ver ejemplos de request/response

---

## 🔧 TROUBLESHOOTING

### Error: `No module named 'fastapi'`

**Solución:**
```powershell
.\azca_310_env\Scripts\Activate.ps1
pip install fastapi uvicorn pydantic sqlalchemy python-dotenv
```

---

### Error: `Connection refused` al conectar con BD

**Esto es normal.** Significa:
1. La API funciona ✅
2. Pero la BD no está disponible (credenciales inválidas o servidor down)

**Para debug:**
- Verifica que el `.env` tiene credenciales correctas
- Prueba conectarte directamente a Azure SQL desde SSMS
- Comprueba los logs de la API

---

### Error: `ODBC driver not found`

**Solución:**
```powershell
# Instalar driver ODBC para SQL Server
pip install pyodbc

# En Windows, descargar: https://learn.microsoft.com/en-us/sql/connect/odbc/windows/
```

---

### La API inicia pero `/predict` falla con import error

**Causa:** El motor de predicción (PredictionEngine) necesita las librerías de ML

**Solución:**
```powershell
pip install pandas scikit-learn xgboost
```

---

## 📊 FLUJO COMPLETO

```
Cliente HTTP
    ↓
POST /predict (JSON)
    ↓
FastAPI (Pydantic valida)
    ↓
PredictionEngine.predict() (ML)
    ↓
SQLAlchemy ORM (crea registro)
    ↓
Azure SQL (INSERT PredictionLogs)
    ↓
Response JSON
    ↓
Cliente HTTP
```

---

## 🎯 CHECKLIST FINAL

Antes de dar por completada la prueba:

- [ ] La API inicia sin errores
- [ ] `GET /health` retorna 200 OK
- [ ] `POST /predict` retorna 200 OK
- [ ] La respuesta incluye `log_id`
- [ ] Los logs en consola muestran "Predicción guardada"
- [ ] Swagger está disponible en `/docs`
- [ ] Los datos inválidos son rechazados (422)
- [ ] La BD recibe el registro (si está configurada)

---

## 📝 Archivos Generados

| Archivo | Descripción |
|---------|------------|
| `azca/db/database.py` | Configuración SQLAlchemy + Azure SQL |
| `azca/db/models.py` | Modelo ORM PredictionLog |
| `azca/api/main.py` | API FastAPI con endpoints |
| `.env` | Credenciales de BD (⚠️ no commitear) |
| `.env.example` | Plantilla de credenciales |
| `run_api.ps1` | Script para iniciar la API |
| `run_api.bat` | Script Windows batch |

---

## 🔗 Links Útiles

- **FastAPI Docs:** https://fastapi.tiangolo.com/
- **SQLAlchemy Docs:** https://docs.sqlalchemy.org/
- **Azure SQL:** https://azure.microsoft.com/sql-database
- **Uvicorn:** https://www.uvicorn.org/

---

## ❓ Preguntas Frecuentes

**¿Dónde se guardan los logs de predicciones?**
→ En la tabla `PredictionLogs` de Azure SQL

**¿Puedo probar sin BD?**
→ No completamente, pero puedes ver los logs en consola

**¿Cómo reinicio la API?**
→ Presiona Ctrl+C en la terminal y vuelve a ejecutar `uvicorn`

**¿Dónde está la documentación de la API?**
→ En http://localhost:8000/docs (Swagger automático)

---

✅ **¡Lista la API para testing!**
