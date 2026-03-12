import pandas as pd
import os
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import OrdinalEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score

# 1. Ruta absoluta al archivo avanzado (asegúrate de usar el que ya está mezclado/shuffled si lo tienes)
directorio_actual = os.path.dirname(os.path.abspath(__file__))
ruta_entrada = os.path.abspath(os.path.join(directorio_actual, '../../../csv/menu_history_advanced_shuffled.csv'))

df = pd.read_csv(ruta_entrada)

# 2. Definir el target y hacer DROP de lo que sobra
target = 'menu_starter'

# ELIMINAMOS: El propio target para que no haga trampa, y los platos futuros (principal y postre)
# También quitamos 'restaurant_id' y 'service_date' porque ya hemos extraído su valor útil
columnas_a_eliminar = ['restaurant_id', 'service_date', 'menu_main', 'menu_dessert', target]

X = df.drop(columns=columnas_a_eliminar)
y = df[target]

# 3. Separar datos
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# 4. Pipeline: Detectar automáticamente columnas de texto (object) para codificarlas
categorical_cols = X.select_dtypes(include=['object']).columns.tolist()

preprocessor = ColumnTransformer(
    transformers=[
        ('cat', OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1), categorical_cols)
    ], remainder='passthrough'
)

modelo_entrante = Pipeline(steps=[
    ('preprocessor', preprocessor),
    ('classifier', RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1))
])

# 5. Entrenar y evaluar
print("Entrenando Modelo 1: Entrante...")
modelo_entrante.fit(X_train, y_train)
y_pred = modelo_entrante.predict(X_test)

print(f"✅ Accuracy del modelo ENTRANTE: {accuracy_score(y_test, y_pred) * 100:.2f}%\n")