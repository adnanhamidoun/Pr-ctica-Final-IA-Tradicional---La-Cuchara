import pickle
import pandas as pd
from datetime import datetime

# 1. Cargar el "cerebro"
print("Cargando el modelo de Azca...")
with open('model.pkl', 'rb') as f:
    modelo = pickle.load(f)

# 2. Los 24 ingredientes que la IA exige (con valores de prueba)
datos_dict = {
    'service_date': [datetime(2026, 3, 15)], # Una fecha cualquiera
    'restaurant_id': [101],
    'max_temp_c': [22.5],
    'precipitation_mm': [0.0],
    'is_rain_service_peak': [False],
    'is_stadium_event': [False],
    'is_azca_event': [False],
    'is_holiday': [False],
    'is_bridge_day': [False],
    'is_payday_week': [True],  # ¡Semana de cobrar!
    'is_business_day': [True],
    'services_lag_7': [110],   # Lo que pasó hace una semana
    'avg_4_weeks': [105.5],
    'capacity_limit': [150],
    'table_count': [40],
    'min_service_duration': [45],
    'terrace_setup_type': ['standard'],
    'opens_weekends': [True],
    'has_wifi': [True],
    'restaurant_segment': ['casual'],
    'menu_price': [14.50],
    'dist_office_towers': [200], # Metros a las oficinas
    'google_rating': [4.6],
    'cuisine_type': ['mediterranean']
}

# Convertimos a DataFrame (el formato que entiende la IA)
df_test = pd.DataFrame(datos_dict)

# 3. ¡LA PREDICCIÓN!
print("Calculando servicios previstos...")
try:
    prediccion = modelo.predict(df_test)
    print("\n" + "="*40)
    print(f" RESULTADO FINAL: {int(prediccion[0])} personas/servicios")
    print("="*40)
    print("¡Felicidades Adnan! Tu IA local funciona gratis.")
except Exception as e:
    print(f"\nError en la predicción: {e}")