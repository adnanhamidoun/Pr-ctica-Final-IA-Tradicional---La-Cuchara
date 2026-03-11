"""
Script de prueba para validar la API y la integración con base de datos.

Ejecuta con:
    python azca/tests/test_integration.py
"""

import sys
from pathlib import Path

# Agregar el root del proyecto al path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

print("\n" + "=" * 80)
print("🧪 PRUEBA DE INTEGRACIÓN - AZCA Prediction API")
print("=" * 80 + "\n")

# ============================================================================
# Test 1: Verificar imports básicos
# ============================================================================
print("✓ Test 1: Importar módulos básicos")
try:
    from dotenv import load_dotenv
    print("  ✅ dotenv importado")
    load_dotenv(project_root / ".env")
    print("  ✅ Variables de entorno cargadas")
except Exception as e:
    print(f"  ❌ Error: {e}")
    sys.exit(1)

# ============================================================================
# Test 2: Verificar configuración de BD
# ============================================================================
print("\n✓ Test 2: Configuración de base de datos")
try:
    import os
    db_server = os.getenv("DB_SERVER")
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    
    if db_server and db_name and db_user:
        print(f"  ✅ DB_SERVER: {db_server}")
        print(f"  ✅ DB_NAME: {db_name}")
        print(f"  ✅ DB_USER: {db_user}")
    else:
        print("  ⚠️  Algunas variables de BD están vacías (normal en primer test)")
except Exception as e:
    print(f"  ❌ Error: {e}")

# ============================================================================
# Test 3: Importar módulos de BD
# ============================================================================
print("\n✓ Test 3: Importar módulos de base de datos")
try:
    from azca.db.database import engine, Base, SessionLocal
    print("  ✅ database.py importado correctamente")
    from azca.db.models import PredictionLog
    print("  ✅ models.py importado correctamente")
    from azca.db import get_db, init_db
    print("  ✅ Funciones de BD importadas")
except Exception as e:
    print(f"  ❌ Error: {e}")
    sys.exit(1)

# ============================================================================
# Test 4: Importar motor de predicción
# ============================================================================
print("\n✓ Test 4: Importar motor de predicción")
try:
    from azca.core import PredictionEngine
    print("  ✅ PredictionEngine importado")
except Exception as e:
    print(f"  ❌ Error: {e}")
    sys.exit(1)

# ============================================================================
# Test 5: Importar API FastAPI
# ============================================================================
print("\n✓ Test 5: Importar API FastAPI")
try:
    from azca.api.main import app, PredictionRequest, PredictionResponse
    print("  ✅ FastAPI app importado")
    print("  ✅ Modelos Pydantic importados")
except Exception as e:
    print(f"  ❌ Error: {e}")
    sys.exit(1)

# ============================================================================
# Test 6: Validar esquema Pydantic
# ============================================================================
print("\n✓ Test 6: Validar esquema Pydantic")
try:
    from datetime import date
    
    request_data = {
        "service_date": date(2026, 3, 15),
        "max_temp_c": 28.5,
        "precipitation_mm": 0.0,
        "is_stadium_event": False,
        "is_payday_week": True,
    }
    
    # Intentar crear una instancia
    prediction_request = PredictionRequest(**request_data)
    print(f"  ✅ PredictionRequest válido: {prediction_request}")
    
except Exception as e:
    print(f"  ❌ Error en validación: {e}")
    sys.exit(1)

# ============================================================================
# Test 7: Verificar endpoints
# ============================================================================
print("\n✓ Test 7: Verificar endpoints FastAPI")
try:
    routes = [route.path for route in app.routes]
    expected_routes = ["/health", "/predict", "/"]
    
    for route in expected_routes:
        if any(route in r for r in routes):
            print(f"  ✅ Endpoint {route} registrado")
        else:
            print(f"  ⚠️  Endpoint {route} no encontrado")
            
except Exception as e:
    print(f"  ❌ Error: {e}")

# ============================================================================
# Test 8: Probar conexión a BD (opcional)
# ============================================================================
print("\n✓ Test 8: Probar conexión a base de datos")
try:
    db_server = os.getenv("DB_SERVER")
    if "your_server" in db_server or not db_server:
        print("  ⚠️  Credenciales de BD no configuradas (usar .env real)")
    else:
        print("  🔄 Intentando conectar...")
        try:
            with engine.connect() as conn:
                result = conn.execute("SELECT 1")
                print("  ✅ Conexión exitosa a Azure SQL")
        except Exception as db_error:
            print(f"  ⚠️  No se pudo conectar: {str(db_error)[:100]}")
            print("     (Esto es normal si las credenciales no son válidas)")
except Exception as e:
    print(f"  ❌ Error: {e}")

# ============================================================================
# RESUMEN
# ============================================================================
print("\n" + "=" * 80)
print("✅ PRUEBAS COMPLETADAS")
print("=" * 80)
print("""
📋 Próximos pasos:

1. Configurar el archivo .env real con tus credenciales de Azure SQL
2. Ejecutar la API:
   uvicorn azca.api.main:app --reload

3. Probar los endpoints:
   GET  http://localhost:8000/health
   POST http://localhost:8000/predict

4. Ver documentación interactiva:
   http://localhost:8000/docs

5. Ejecutar tests unitarios:
   pytest azca/tests/
""")
print("=" * 80 + "\n")
