import numpy as np
import pandas as pd
from datetime import datetime, timedelta

duracion_horas = 24
frecuencia_seg = 0.5
num_puntos = int(duracion_horas * 3600 / frecuencia_seg)

t_seg = np.arange(0, duracion_horas * 3600, frecuencia_seg)
hora = t_seg / 3600.0

np.random.seed(42)

# Perfil base de corriente (m/s) — flujo fluvial realista
# Madrugada: caudal base estable, mediodía: ligero incremento
# por deshielo/lluvia, noche: descenso gradual
vc_base = (
    2.0
    + 0.8 * np.sin(np.pi * (hora - 10) / 12)  # pico suave al mediodía
    + 0.3 * np.sin(2 * np.pi * hora / 24 - 0.5) # componente semidiurna
)
vc_base = np.clip(vc_base, 1.5, 3.5)

# Turbulencia: ruido gaussiano con correlación temporal (autoregresivo)
ruido_blanco = np.random.normal(0, 1.0, size=num_puntos)
ruido_filtrado = np.zeros_like(ruido_blanco)
alpha = 0.98
ruido_filtrado[0] = ruido_blanco[0]
for i in range(1, num_puntos):
    ruido_filtrado[i] = alpha * ruido_filtrado[i-1] + (1 - alpha) * ruido_blanco[i]
ruido = ruido_filtrado * 0.15

vc = vc_base + ruido
vc = np.clip(vc, 1.2, 4.0)

# Crecidas ocasionales (eventos de 10-30 minutos)
num_crecidas = np.random.poisson(4)
for _ in range(num_crecidas):
    inicio = np.random.randint(0, num_puntos - 3600)
    duracion = np.random.randint(1200, 3600)
    intensidad = np.random.uniform(0.5, 1.5)
    vc[inicio:inicio+duracion] = np.clip(
        vc[inicio:inicio+duracion] + intensidad *
        np.exp(-np.linspace(0, 3, duracion)**2),
        1.2, 4.0
    )

df = pd.DataFrame({
    'timestamp': [datetime(2023, 1, 1) + timedelta(seconds=s) for s in t_seg],
    'Vc': vc,
})

df.to_csv('datos_meteorologicos_hidricos_sinteticos.csv', index=False, float_format='%.2f')

print(f"Generados {len(df)} registros.")
print(df.head(10))
print("\nEstadisticas:")
print(df[['Vc']].describe())
