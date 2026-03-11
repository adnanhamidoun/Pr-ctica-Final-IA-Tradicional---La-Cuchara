# Azca ML Service

Model-as-a-Service prediction engine para servicios de restaurante.

## 🚀 Quickstart

### 1. Clone & Setup

```bash
git clone https://github.com/tu-usuario/azca.git
cd azca

# Create virtual environment
python -m venv venv
source venv/Scripts/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# For development (testing, jupyter)
pip install -r requirements-dev.txt
```

### 2. Run Tests

```bash
# Unit tests
pytest azca/tests/test_core.py -v

# Integration test
pytest azca/tests/test_integration.py -v

# All tests
pytest azca/tests/ -v

# Manual verification script (no framework needed)
python azca/tests/manual_test.py
```

### 3. Quick Prediction

```python
from datetime import datetime
from azca.core.engine import PredictionEngine

engine = PredictionEngine(pipeline_config={
    "restaurant_id": 101,
    "menu_price": 14.5,
    "dist_office_towers": 200,
})

prediction = engine.predict("model", {
    "service_date": datetime(2026, 3, 15),
    "max_temp_c": 25.0,
    "is_stadium_event": True,
    "is_payday_week": True,
})
print(f"Predicted services: {prediction}")
```

---

## 📁 Project Structure

```
azca/
├── core/
│   ├── manager.py          # ModelProvider: load & cache models
│   ├── pipeline.py         # InferencePipeline: feature engineering
│   ├── engine.py           # PredictionEngine: orchestration
│   └── __init__.py
├── api/                     # FastAPI endpoints (coming soon)
├── ui/                      # Frontend (coming soon)
├── artifacts/
│   ├── model.pkl           # Trained model
│   └── MLmodel/            # Azure AutoML metadata
└── tests/
    ├── test_core.py        # Unit tests (12 tests)
    ├── test_integration.py # E2E test
    └── manual_test.py      # Manual verification script
```

---

## 🔧 Architecture

### ModelProvider
- Loads `.pkl` models from `artifacts/`
- Caches loaded models in memory (no disk I/O on repeat calls)
- Supports custom artifact paths

### InferencePipeline
- Transforms 6 basic inputs → 24 feature columns (Azure AutoML format)
- Auto-detects: rain peaks (>10mm), business days
- Configurable restaurant defaults

### PredictionEngine
- Combines ModelProvider + InferencePipeline
- Single `predict(model_name, data)` method
- Returns integer prediction (services count)

---

## ✅ Testing

**12 tests** verify:
- Model load & caching
- Feature transformation (shape, columns, logic)
- Complete prediction pipeline
- Multiple scenarios (golden day, rain, winter, holiday)

**All passing** ✓

---

## 📦 Dependencies

**Production:**
- `numpy`, `pandas`, `scikit-learn`, `scipy`
- `azureml-*` (AutoML models)
- `fastapi`, `uvicorn`, `pydantic`

**Development:**
- `pytest` (testing)
- `jupyter` (notebooks)
- `black`, `flake8`, `mypy` (optional code quality)

Pinned versions in `requirements.txt` ensure reproducibility.

---

## 🚧 Next Steps

1. **API** (`azca/api/app.py`): FastAPI endpoints
2. **UI** (`azca/ui/`): Dashboard for predictions
3. **Logging**: Debug trails for model loads & predictions
4. **Error handling**: Input validation & custom exceptions

---

## 🔗 Links

- Model: `azca/artifacts/model.pkl`
- Tests: `azca/tests/`
