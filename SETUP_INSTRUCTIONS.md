## 🚀 INSTRUCCIONES PARA EJECUTAR LA API

El entorno virtual `azca_310_env` necesita ser reconfigurado. Aquí está la solución:

### OPCIÓN 1: Usar Conda (Si lo tienes instalado)

```bash
# 1. Activa el entorno conda
conda activate azca_310_env

# 2. Instala las dependencias que faltan
pip install sqlalchemy python-dotenv fastapi uvicorn

# 3. Ejecuta la API
uvicorn azca.api.main:app --reload --host 0.0.0.0 --port 8000
```

### OPCIÓN 2: Crear un nuevo entorno virtual (Recomendado)

```bash
# 1. Crea un nuevo entorno
python -m venv azca_env_new

# 2. Actía
# En Windows PowerShell:
.\azca_env_new\Scripts\Activate.ps1

# 3. Instala todas las dependencias
pip install -r requirements.txt
pip install fastapi uvicorn sqlalchemy python-dotenv

# 4. Ejecuta la API
uvicorn azca.api.main:app --reload
```

### OPCIÓN 3: Usar Python Global (Rápido para testear)

```bash
# Instala las librerías globally
pip install fastapi uvicorn sqlalchemy python-dotenv pydantic

# Ejecuta
uvicorn azca.api.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 📌 Después de ejecutar la API:

1. **Abre en el navegador:**
   ```
   http://localhost:8000/docs
   ```

2. **Prueba el health check:**
   ```bash
   curl http://localhost:8000/health
   ```

3. **Prueba una predicción:**
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

---

## ✅ Lo que ya está 100% completado:

- ✅ `azca/db/database.py` - Conexión a Azure SQL con SQLAlchemy
- ✅ `azca/db/models.py` - Modelo ORM PredictionLog completo
- ✅ `azca/api/main.py` - API FastAPI con 2 endpoints profesionales
- ✅ `.env` - Configurado con credenciales
- ✅ Documentación y guías

Todo el código está listo. Solo necesitas instalar las dependencias de Python.
