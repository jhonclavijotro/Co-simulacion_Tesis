import numpy as np
import pandas as pd
from datetime import datetime, timedelta

duracion_horas = 24
frecuencia_seg = 0.5
num_puntos = int(duracion_horas * 3600 / frecuencia_seg)

t_seg = np.arange(0, duracion_horas * 3600, frecuencia_seg)
hora = t_seg / 3600.0

np.random.seed(42)

# Perfil de consigna de velocidad (rad/s) — simula regulacion frecuencia
# 188.5 rad/s = 1800 RPM (base para generador 60Hz 4-pol os)
pref_base = 188.5

# Variacion diurna tipica: ligera caida nocturna (menos carga),
# recuperacion en horas pico
pref = (
    pref_base
    + 0.3 * np.sin(2 * np.pi * (hora - 6) / 24)  # minimo nocturno
    - 0.1 * np.sin(np.pi * (hora - 14) / 8)        # maximo diurno
)

# Ruido de alta frecuencia (regulacion fina)
ruido = np.random.normal(0, 0.05, size=num_puntos)
pref += ruido

# Eventos de contingencia (caidas/bajones de frecuencia)
num_eventos = np.random.poisson(6)
for _ in range(num_eventos):
    inicio = np.random.randint(0, num_puntos - 1200)
    duracion = np.random.randint(200, 1200)
    magnitud = np.random.choice([-2.0, -1.0, 1.0, 1.5])
    pref[inicio:inicio+duracion] += magnitud * np.exp(
        -np.linspace(0, 4, duracion)**2
    )

pref = np.clip(pref, 182.0, 195.0)

df = pd.DataFrame({
    'timestamp': [datetime(2023, 1, 1) + timedelta(seconds=s) for s in t_seg],
    'pref': pref,
})

df.to_csv('consignas_diesel_sinteticas.csv', index=False, float_format='%.4f')

print(f"Generados {len(df)} registros.")
print(df.head(10))
print("\nEstadisticas:")
print(df[['pref']].describe())
