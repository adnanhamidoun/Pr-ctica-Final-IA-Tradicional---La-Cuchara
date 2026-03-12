import pandas as pd
import os

# 1. Crear rutas robustas
# 'directorio_actual' es la carpeta 'menus'
directorio_actual = os.path.dirname(os.path.abspath(__file__))

# Subimos DOS niveles ('../../') para salir de 'menus', salir de 'scripts', y entrar a 'csv'
ruta_entrada = os.path.abspath(os.path.join(directorio_actual, '../../../csv/menu_history_clean.csv'))
ruta_salida = os.path.abspath(os.path.join(directorio_actual, '../../../csv/menu_history_advanced_features.csv'))

# Imprimimos la ruta para comprobar que ahora apunta bien antes de leer
print(f"Buscando el archivo en: {ruta_entrada}")

# 2. Cargar los datos limpios usando la ruta dinámica
df = pd.read_csv(ruta_entrada)

# 3. Convertir la columna de fecha a formato 'datetime'
df['service_date'] = pd.to_datetime(df['service_date'])

# 4. Extraer el día de la semana y el mes
df['day_of_week'] = df['service_date'].dt.dayofweek 
df['month'] = df['service_date'].dt.month

# 5. ORDENAR LOS DATOS (Paso crítico)
df = df.sort_values(by=['restaurant_id', 'service_date']).reset_index(drop=True)

# 6. Crear variables: "Platos del día anterior" 
df['starter_yesterday'] = df.groupby('restaurant_id')['menu_starter'].shift(1)
df['main_yesterday'] = df.groupby('restaurant_id')['menu_main'].shift(1)
df['dessert_yesterday'] = df.groupby('restaurant_id')['menu_dessert'].shift(1)

# 7. Crear variables: "Platos de la semana pasada"
df['starter_last_week'] = df.groupby(['restaurant_id', 'day_of_week'])['menu_starter'].shift(1)
df['main_last_week'] = df.groupby(['restaurant_id', 'day_of_week'])['menu_main'].shift(1)
df['dessert_last_week'] = df.groupby(['restaurant_id', 'day_of_week'])['menu_dessert'].shift(1)

# 8. Limpieza final
df.fillna('Desconocido', inplace=True)

# 9. Guardar el nuevo dataset
df.to_csv(ruta_salida, index=False)

print(f"¡Transformación completada con éxito! Archivo guardado en: {ruta_salida}")