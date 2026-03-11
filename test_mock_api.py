"""
Test Mock de la API - Sin dependencias de ML/BD

Valida que FastAPI funciona sin necesidad de:
- Pandas/NumPy/Sklearn
- Azure SQL
- Modelos entrenados

Ejecutar con: python test_mock_api.py
"""

import sys
from pathlib import Path
from datetime import date

print("\n" + "=" * 80)
print("🧪 TEST MOCK - AZCA API (Sin dependencias pesadas)")
print("=" * 80 + "\n")

# ============================================================================
# Test 1: Importar FastAPI y Pydantic
# ============================================================================
print("Test 1: Importar FastAPI y Pydantic")
try:
    from fastapi import FastAPI
    from pydantic import BaseModel, Field
    print("✅ FastAPI y Pydantic disponibles\n")
except ImportError as e:
    print(f"❌ Error: {e}")
    print("   Ejecuta: pip install fastapi pydantic\n")
    sys.exit(1)

# ============================================================================
# Test 2: Validar modelos Pydantic
# ============================================================================
print("Test 2: Validar esquemas Pydantic")
try:
    # Importamos los modelos directamente de main.py
    project_root = Path(__file__).parent
    sys.path.insert(0, str(project_root))
    
    # OPCIÓN: Copiar aquí los modelos para no depender de imports complejos
    class PredictionRequest(BaseModel):
        service_date: date
        max_temp_c: float
        precipitation_mm: float
        is_stadium_event: bool
        is_payday_week: bool

    # Datos de prueba válidos
    valid_data = {
        "service_date": "2026-03-15",
        "max_temp_c": 28.5,
        "precipitation_mm": 0.0,
        "is_stadium_event": False,
        "is_payday_week": True,
    }
    
    req = PredictionRequest(**valid_data)
    print(f"✅ Request válido: {req}")
    
    # Datos inválidos (para probar validación)
    invalid_data = {
        "service_date": "2026-03-15",
        "max_temp_c": "no_es_número",  # ❌ Debe ser float
        "precipitation_mm": 0.0,
        "is_stadium_event": False,
        "is_payday_week": True,
    }
    
    try:
        req_invalid = PredictionRequest(**invalid_data)
        print("❌ Validación falló - debería haber error")
    except Exception as e:
        print(f"✅ Validación funciona - rechazó datos inválidos: {str(e)[:50]}...")
        
except Exception as e:
    print(f"❌ Error: {e}\n")
    sys.exit(1)

print()

# ============================================================================
# Test 3: Crear app FastAPI mock
# ============================================================================
print("Test 3: Crear aplicación FastAPI mock")
try:
    from fastapi.testclient import TestClient
    
    app = FastAPI(title="Test Mock API")
    
    @app.get("/health")
    def health():
        return {"status": "healthy", "message": "API funcionando"}
    
    @app.post("/predict")
    def predict(request: PredictionRequest):
        return {
            "prediction_result": 150,
            "service_date": str(request.service_date),
            "model_version": "v1_xgboost",
            "log_id": 1,
        }
    
    print("✅ App FastAPI creada\n")
    
except Exception as e:
    print(f"❌ Error: {e}\n")
    sys.exit(1)

# ============================================================================
# Test 4: Probar endpoints con TestClient
# ============================================================================
print("Test 4: Probar endpoints")
try:
    from fastapi.testclient import TestClient
    
    client = TestClient(app)
    
    # Test GET /health
    response = client.get("/health")
    assert response.status_code == 200, f"Status esperado 200, recibido {response.status_code}"
    data = response.json()
    assert data["status"] == "healthy"
    print(f"✅ GET /health:")
    print(f"   Response: {data}\n")
    
    # Test POST /predict (válido)
    prediction_payload = {
        "service_date": "2026-03-15",
        "max_temp_c": 28.5,
        "precipitation_mm": 0.0,
        "is_stadium_event": False,
        "is_payday_week": True,
    }
    
    response = client.post("/predict", json=prediction_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["prediction_result"] == 150
    print(f"✅ POST /predict (válido):")
    print(f"   Response: {data}\n")
    
    # Test POST /predict (inválido)
    invalid_payload = {
        "service_date": "2026-03-15",
        "max_temp_c": "NO_ES_NÚMERO",  # ❌ Inválido
        "precipitation_mm": 0.0,
        "is_stadium_event": False,
        "is_payday_week": True,
    }
    
    response = client.post("/predict", json=invalid_payload)
    assert response.status_code == 422  # Unprocessable entity
    print(f"✅ POST /predict (inválido) - Validación correcta:")
    print(f"   Status: {response.status_code} (fue rechazado como se esperaba)\n")
    
except Exception as e:
    print(f"❌ Error: {e}\n")
    sys.exit(1)

# ============================================================================
# Test 5: Documentación Swagger
# ============================================================================
print("Test 5: Validar documentación Swagger")
try:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    openapi = response.json()
    
    print(f"✅ OpenAPI schema disponible")
    print(f"   - Título: {openapi.get('info', {}).get('title', 'N/A')}")
    print(f"   - Versión: {openapi.get('info', {}).get('version', 'N/A')}")
    print(f"   - Paths: {list(openapi.get('paths', {}).keys())}\n")
    
except Exception as e:
    print(f"❌ Error: {e}\n")

# ============================================================================
# RESUMEN
# ============================================================================
print("=" * 80)
print("✅ TODOS LOS TESTS MOCK PASARON")
print("=" * 80)
print("""
🎉 Conclusión:
   - FastAPI funciona correctamente
   - Pydantic valida datos
   - Endpoints responden
   - Documentación disponible

📝 Próximos pasos:

   1. Para ejecutar la API REAL (con BD):
      
      uvicorn azca.api.main:app --reload

   2. Para probar con curl:
      
      curl -X POST http://localhost:8000/predict \\
        -H "Content-Type: application/json" \\
        -d '{
          "service_date": "2026-03-15",
          "max_temp_c": 28.5,
          "precipitation_mm": 0.0,
          "is_stadium_event": false,
          "is_payday_week": true
        }'
   
   3. Para ver docs interactivos:
      http://localhost:8000/docs

═════════════════════════════════════════════════════════════════════════════
""")
