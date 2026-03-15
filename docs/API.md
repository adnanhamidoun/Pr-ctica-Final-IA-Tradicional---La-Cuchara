# API Documentation

## Base URL

```
http://127.0.0.1:8000  (Development)
https://azca-api.azurewebsites.net  (Production - example)
```

## Endpoints

### 1. Health Check

**GET** `/health`

Check API status and dependencies.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "environment": "development",
  "timestamp": "2026-03-12T12:34:56Z"
}
```

---

### 2. List Restaurants

**GET** `/restaurants`

Get all available restaurants for dropdown selection.

**Response (200 OK):**
```json
{
  "count": 20,
  "restaurants": [
    {
      "restaurant_id": 1,
      "name": "Restaurant A"
    },
    {
      "restaurant_id": 2,
      "name": "Restaurant B"
    }
  ]
}
```

---

### 3. Get Restaurant Details

**GET** `/restaurants/{restaurant_id}`

Get all parameters for a specific restaurant (auto-populates form).

**Path Parameters:**
- `restaurant_id` (integer): Restaurant ID from dropdown

**Response (200 OK):**
```json
{
  "restaurant_id": 1,
  "name": "Restaurante Premium",
  "capacity_limit": 150,
  "table_count": 12,
  "min_service_duration": 45,
  "terrace_setup_type": "outdoor",
  "opens_weekends": true,
  "has_wifi": true,
  "restaurant_segment": "fine_dining",
  "menu_price": 42.50,
  "dist_office_towers": 250,
  "google_rating": 4.8,
  "cuisine_type": "spanish"
}
```

**Error Response (404 Not Found):**
```json
{
  "detail": "Restaurant with ID 999 not found"
}
```

---

### 4. Create Prediction

**POST** `/predict`

Generate a demand prediction for a restaurant on a specific date.

**Request Body:**
```json
{
  "service_date": "2026-03-15",
  "restaurant_id": 1,
  "capacity_limit": 150,
  "table_count": 12,
  "min_service_duration": 45,
  "terrace_setup_type": "outdoor",
  "opens_weekends": true,
  "has_wifi": true,
  "restaurant_segment": "fine_dining",
  "menu_price": 42.50,
  "dist_office_towers": 250,
  "google_rating": 4.8,
  "cuisine_type": "spanish",
  "is_stadium_event": false,
  "is_azca_event": false
}
```

**Auto-Calculated Fields (Backend):**
- `max_temp_c`: From Open-Meteo API
- `precipitation_mm`: From Open-Meteo API
- `is_rain_service_peak`: Calculated from weather data
- `is_business_day`: From calendar logic
- `is_holiday`: From Spanish holidays (Madrid)
- `is_bridge_day`: From calendar logic
- `is_payday_week`: Days 25-31 of month
- `services_lag_7`: From historical database
- `avg_4_weeks`: From historical database

**Response (201 Created):**
```json
{
  "prediction_result": 87,
  "service_date": "2026-03-15",
  "model_version": "v1_xgboost",
  "execution_timestamp": "2026-03-12T12:34:56Z",
  "log_id": 42
}
```

**Response Fields:**
- `prediction_result` (integer): Forecasted number of services for that date
- `service_date` (string, ISO 8601): The date requested
- `model_version` (string): Model identifier (for tracking)
- `execution_timestamp` (datetime): When prediction was made
- `log_id` (integer): Audit log ID for traceability

**Error Response (422 Unprocessable Entity):**
```json
{
  "detail": "Error in data: invalid service_date format"
}
```

---

### 5. Upload Menu (OCR) + Predict Dishes

**POST** `/predict/menu-upload`

Sube un menú en archivo (PDF/imagen), extrae automáticamente `entrante/principal/postre` con Azure Document Intelligence y devuelve top-3 predicciones por categoría.

**Request (multipart/form-data):**
- `restaurant_id` (integer)
- `service_date` (string, YYYY-MM-DD)
- `menu_file` (file)

**Required environment variables (backend):**
- `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`
- `AZURE_DOCUMENT_INTELLIGENCE_KEY`
- `AZURE_DOCUMENT_INTELLIGENCE_MODEL_ID` (optional, default: `prebuilt-layout`)

**Response (201 Created):**
```json
{
  "restaurant_id": 1,
  "service_date": "2026-03-15",
  "ocr_provider": "azure_document_intelligence",
  "extracted_menu": {
    "starter": "Ensalada César",
    "main": "Merluza a la Gallega",
    "dessert": "Flan Casero"
  },
  "starter_prediction": [
    {"rank": 1, "name": "Ensalada César", "score": 0.91}
  ],
  "main_prediction": [
    {"rank": 1, "name": "Merluza a la Gallega", "score": 0.88}
  ],
  "dessert_prediction": [
    {"rank": 1, "name": "Flan Casero", "score": 0.85}
  ],
  "model_version": "azca_menu_v2",
  "execution_timestamp": "2026-03-14T10:30:00"
}
```

**Error Response (503 Service Unavailable):**
```json
{
  "detail": "Faltan AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT o AZURE_DOCUMENT_INTELLIGENCE_KEY."
}
```

---

## Data Flow Diagram

```
Frontend (React)
    |
    ├─ GET /restaurants ────────┐
    |                           |
    ├─ GET /restaurants/{id} ───┤──→ Backend (FastAPI)
    |                           |        ├─ Fetch from Azure SQL
    └─ POST /predict ───────────┤        ├─ Call Open-Meteo API
                                |        ├─ Calculate calendar features
                                └────→   ├─ Query historical data
                                         └─ Predict with XGBoost
                                             └─ Log to audit table
```

---

## Common Use Cases

### 1. Load Restaurants for Dropdown
```bash
curl http://127.0.0.1:8000/restaurants
```

### 2. Auto-Populate Form
```bash
curl http://127.0.0.1:8000/restaurants/1
```

### 3. Make Prediction
```bash
curl -X POST http://127.0.0.1:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "service_date": "2026-03-15",
    "restaurant_id": 1,
    "capacity_limit": 150,
    "table_count": 12,
    "min_service_duration": 45,
    "terrace_setup_type": "outdoor",
    "opens_weekends": true,
    "has_wifi": true,
    "restaurant_segment": "fine_dining",
    "menu_price": 42.50,
    "dist_office_towers": 250,
    "google_rating": 4.8,
    "cuisine_type": "spanish",
    "is_stadium_event": false,
    "is_azca_event": false
  }'
```

---

## Error Codes

| Code | Meaning | Example |
|------|---------|---------|
| 200 | OK - Request successful | GET /health ✓ |
| 201 | Created - Resource created | POST /predict ✓ |
| 400 | Bad Request - Invalid params | Missing required field |
| 404 | Not Found - Resource missing | Restaurant ID doesn't exist |
| 422 | Unprocessable Entity - Validation failed | Invalid data type |
| 500 | Server Error - Internal issue | Database connection failed |
| 503 | Service Unavailable - Dependency down | ML model not loaded |

---

## Rate Limiting

Currently **no rate limiting** implemented. For production, add:
- 100 requests/minute per IP
- 10,000 requests/day per API key

---

## Authentication

Currently **no authentication**. For production, add:
- Azure AD integration
- API Key management
- JWT tokens

See [DEPLOYMENT.md](./DEPLOYMENT.md) for security recommendations.
