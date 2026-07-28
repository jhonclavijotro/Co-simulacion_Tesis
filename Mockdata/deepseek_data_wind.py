import numpy as np
import pandas as pd
from datetime import datetime, timedelta

duracion_horas = 24
frecuencia_seg = 0.5
num_puntos = int(duracion_horas * 3600 / frecuencia_seg)

t_seg = np.arange(0, duracion_horas * 3600, frecuencia_seg)
hora = t_seg / 3600.0

np.random.seed(42)

# Perfil base de viento (m/s) — patrón diurno realista
# Madrugada: vientos ligeros, mediodía: incremento, tarde: máximos, noche: descenso
ws_base = (
    8.0
    + 1.5 * np.sin(np.pi * (hora - 8) / 10)  # pico suave en la tarde
    + 0.5 * np.sin(2 * np.pi * hora / 24)     # componente semidiurna
)
ws_base = np.clip(ws_base, 8.0, 12.0)

# Turbulencia: ruido gaussiano con correlación temporal (autoregresivo)
ruido_blanco = np.random.normal(0, 1.0, size=num_puntos)
# Filtro pasa-bajos simple para correlacionar el ruido
ruido_filtrado = np.zeros_like(ruido_blanco)
alpha = 0.95
ruido_filtrado[0] = ruido_blanco[0]
for i in range(1, num_puntos):
    ruido_filtrado[i] = alpha * ruido_filtrado[i-1] + (1 - alpha) * ruido_blanco[i]
ruido = ruido_filtrado * 0.5

ws = ws_base + ruido
ws = np.clip(ws, 7.0, 13.0)

# Ráfagas ocasionales (eventos de 2-5 minutos)
num_rafagas = np.random.poisson(8)
for _ in range(num_rafagas):
    inicio = np.random.randint(0, num_puntos - 600)
    duracion = np.random.randint(120, 600)
    intensidad = np.random.uniform(1.0, 2.5)
    ws[inicio:inicio+duracion] = np.clip(
        ws[inicio:inicio+duracion] + intensidad *
        np.exp(-np.linspace(0, 3, duracion)**2),
        7.0, 13.0
    )

df = pd.DataFrame({
    'timestamp': [datetime(2023, 1, 1) + timedelta(seconds=s) for s in t_seg],
    'Ws': ws,
})

df.to_csv('datos_meteorologicos_eolicos_sinteticos.csv', index=False, float_format='%.2f')

print(f"Generados {len(df)} registros.")
print(df.head(10))
print("\nEstadísticas:")
print(df[['Ws']].describe())
