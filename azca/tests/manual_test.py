"""
Manual test script - Run this to interactively verify the system works
"""
import sys
from datetime import datetime
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from azca.core.engine import PredictionEngine
from azca.core.pipeline import InferencePipeline
from azca.core.manager import ModelProvider


def test_1_model_provider():
    """Test 1: Can we load and cache the model?"""
    print("\n" + "="*60)
    print("TEST 1: ModelProvider (Load & Cache)")
    print("="*60)
    
    try:
        provider = ModelProvider()
        print(f"✓ ModelProvider initialized")
        print(f"  Artifacts path: {provider.artifacts_path}")
        print(f"  Cache empty: {len(provider._cache) == 0}")
        
        # Try to load model
        model = provider.get_model("model")
        print(f"✓ Model loaded successfully")
        print(f"  Model type: {type(model).__name__}")
        print(f"  Cache now has: {len(provider._cache)} model(s)")
        
        # Try to get from cache
        model2 = provider.get_model("model")
        print(f"✓ Model retrieved from cache (same object: {model is model2})")
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False


def test_2_pipeline():
    """Test 2: Can we transform inputs into 24-column features?"""
    print("\n" + "="*60)
    print("TEST 2: InferencePipeline (Feature Engineering)")
    print("="*60)
    
    try:
        pipeline = InferencePipeline()
        print(f"✓ Pipeline initialized with defaults")
        print(f"  Fixed fields: {len(pipeline.fixed_fields)} fields")
        print(f"  Expected columns: {len(pipeline.MODEL_COLUMNS)} columns")
        
        # Build features
        data = {
            "service_date": datetime(2026, 3, 15),
            "max_temp_c": 22.5,
            "precipitation_mm": 5,
            "is_stadium_event": True,
            "is_payday_week": True,
        }
        
        df = pipeline.build_features(data)
        print(f"✓ Features built successfully")
        print(f"  DataFrame shape: {df.shape}")
        print(f"  Columns match: {df.shape[1] == 24}")
        
        print("\n  Sample feature values:")
        print(f"    service_date: {df['service_date'].values[0]}")
        print(f"    max_temp_c: {df['max_temp_c'].values[0]}")
        print(f"    precipitation_mm: {df['precipitation_mm'].values[0]}")
        print(f"    is_rain_service_peak: {df['is_rain_service_peak'].values[0]}")
        print(f"    is_business_day: {df['is_business_day'].values[0]}")
        print(f"    menu_price: {df['menu_price'].values[0]}")
        
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False


def test_3_engine_end_to_end():
    """Test 3: Full pipeline - can PredictionEngine predict?"""
    print("\n" + "="*60)
    print("TEST 3: PredictionEngine (E2E Prediction)")
    print("="*60)
    
    try:
        # Azca-specific config
        azca_config = {
            "restaurant_id": 101,
            "capacity_limit": 150,
            "table_count": 40,
            "menu_price": 14.50,
            "dist_office_towers": 200,
            "google_rating": 4.6,
        }
        
        engine = PredictionEngine(pipeline_config=azca_config)
        print(f"✓ PredictionEngine initialized for Azca")
        print(f"  Restaurant ID: {engine.pipeline.fixed_fields['restaurant_id']}")
        print(f"  Menu price: ${engine.pipeline.fixed_fields['menu_price']}")
        
        # Test scenario: Golden day
        data = {
            "service_date": datetime(2026, 3, 15),
            "max_temp_c": 25.0,
            "precipitation_mm": 0,
            "is_stadium_event": True,
            "is_payday_week": True,
        }
        
        prediction = engine.predict("model", data)
        print(f"✓ Prediction generated successfully")
        print(f"  Scenario: Golden day (25°C, no rain, stadium event, payday)")
        print(f"  Predicted services: {prediction}")
        
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False


def test_4_multiple_scenarios():
    """Test 4: Try different scenarios"""
    print("\n" + "="*60)
    print("TEST 4: Multiple Scenarios")
    print("="*60)
    
    azca_config = {
        "restaurant_id": 101,
        "capacity_limit": 150,
        "table_count": 40,
        "menu_price": 14.50,
        "dist_office_towers": 200,
        "google_rating": 4.6,
    }
    
    engine = PredictionEngine(pipeline_config=azca_config)
    
    scenarios = {
        "Golden Day": {
            "service_date": datetime(2026, 3, 15),
            "max_temp_c": 25.0,
            "precipitation_mm": 0,
            "is_stadium_event": True,
            "is_payday_week": True,
        },
        "Rainy Day": {
            "service_date": datetime(2026, 3, 16),
            "max_temp_c": 10.0,
            "precipitation_mm": 25,
            "is_stadium_event": False,
            "is_payday_week": False,
        },
        "Cold Winter": {
            "service_date": datetime(2026, 1, 10),
            "max_temp_c": 2.0,
            "precipitation_mm": 50,
            "is_stadium_event": False,
            "is_payday_week": False,
        },
        "Holiday": {
            "service_date": datetime(2026, 12, 25),
            "max_temp_c": 18.0,
            "precipitation_mm": 0,
            "is_holiday": True,
            "is_payday_week": True,
        },
    }
    
    print()
    try:
        for name, data in scenarios.items():
            pred = engine.predict("model", data)
            temp = data["max_temp_c"]
            rain = data.get("precipitation_mm", 0)
            print(f"  {name:15} | Temp: {temp:5.1f}°C | Rain: {rain:5.1f}mm | → {pred:3d} services")
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False


def main():
    print("\n")
    print("█" * 60)
    print("█  AZCA ML SYSTEM - MANUAL VERIFICATION")
    print("█" * 60)
    
    results = []
    results.append(("ModelProvider", test_1_model_provider()))
    results.append(("InferencePipeline", test_2_pipeline()))
    results.append(("PredictionEngine E2E", test_3_engine_end_to_end()))
    results.append(("Multiple Scenarios", test_4_multiple_scenarios()))
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status} | {name}")
    
    all_passed = all(r[1] for r in results)
    print("\n" + ("█" * 60))
    if all_passed:
        print("█  ALL TESTS PASSED ✓")
    else:
        print("█  SOME TESTS FAILED ✗")
    print("█" * 60 + "\n")
    
    return all_passed


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
