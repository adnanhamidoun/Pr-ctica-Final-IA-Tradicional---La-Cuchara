import pickle
import pandas as pd
from datetime import datetime

# 1. Cargar el modelo
with open('model.pkl', 'rb') as f:
    modelo = pickle.load(f)

def probr_ia():
    print("\n--- SIMULADOR DE AZCA ---")
    temp = float(input("¿Qué temperatura máxima hará? (ej: 22): "))
    lluvia = float(input("¿Cuántos mm de lluvia? (0 si está despejado): "))
    payday = input("¿Es semana de paga? (s/n): ").lower() == 's'
    stadium = input("¿Hay evento en el estadio? (s/n): ").lower() == 's'
    
    # Creamos el diccionario con los 24 campos
    # Ponemos valores 'base' para lo que no cambia
    datos = {
        'service_date': [datetime.now()],
        'restaurant_id': [101],
        'max_temp_c': [temp],
        'precipitation_mm': [lluvia],
        'is_rain_service_peak': [lluvia > 5],
        'is_stadium_event': [stadium],
        'is_azca_event': [False],
        'is_holiday': [False],
        'is_bridge_day': [False],
        'is_payday_week': [payday],
        'is_business_day': [True],
        'services_lag_7': [110], # Dato medio
        'avg_4_weeks': [105.0],
        'capacity_limit': [150],
        'table_count': [40],
        'min_service_duration': [45],
        'terrace_setup_type': ['standard'],
        'opens_weekends': [True],
        'has_wifi': [True],
        'restaurant_segment': ['casual'],
        'menu_price': [14.50],
        'dist_office_towers': [200],
        'google_rating': [4.6],
        'cuisine_type': ['mediterranean']
    }

    df = pd.DataFrame(datos)
    pred = modelo.predict(df)[0]
    
    print(f"\n>>> PREDICCIÓN: {int(pred)} servicios.")
    print("-" * 30)

if __name__ == "__main__":
    while True:
        probr_ia()
        if input("¿Otra prueba? (s/n): ").lower() != 's': break