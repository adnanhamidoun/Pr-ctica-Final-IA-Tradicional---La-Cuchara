import pandas as pd

# 1. Cargar los datos que ya tienen las columnas del "día anterior" y "semana pasada"
df = pd.read_csv('../../../csv/menu_history_advanced_features.csv')

# 2. Mezclar (shuffle) el 100% de las filas de forma aleatoria
# frac=1 significa que cogemos una muestra del 100% de los datos
# random_state=42 es la "semilla", asegura que siempre se mezcle de la misma forma si lo repites
df_shuffled = df.sample(frac=1, random_state=42).reset_index(drop=True)

# 3. Guardar el nuevo dataset mezclado y definitivo
output_file = 'menu_history_advanced_shuffled.csv'
df_shuffled.to_csv(output_file, index=False)

print("¡Datos mezclados con éxito!")
print("\nPrimeras 5 filas del nuevo dataset (fíjate cómo los 'restaurant_id' ahora están saltando):")
print(df_shuffled[['restaurant_id', 'service_date', 'menu_starter']].head())