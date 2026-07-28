import numpy as np
import pandas as pd
from datetime import datetime, timedelta

duracion_horas = 24
frecuencia_seg = 0.5
num_puntos = int(duracion_horas * 3600 / frecuencia_seg)

t_seg = np.arange(0, duracion_horas * 3600, frecuencia_seg)
hora = t_seg / 3600.0

# Radiación POA (perfil gaussiano)
sigma_poa = 3.0
poa_media = 12.0
poa_max = 850.0
poa_sin_ruido = poa_max * np.exp(-0.5 * ((hora - poa_media) / sigma_poa) ** 2)
poa_sin_ruido = np.where((hora >= 6) & (hora <= 18), poa_sin_ruido, 0.0)
ruido_poa = np.random.normal(0, 5, size=num_puntos)
poa = poa_sin_ruido + ruido_poa
poa = np.maximum(poa, 0)

# Temperatura ambiente en Kelvin (20-32 °C → 293.15-305.15 K)
puntos_hora = [0, 6, 10, 14, 18, 24]
puntos_temp_c = [20, 26, 26, 32, 24, 20]
t_amb_c = np.interp(hora, puntos_hora, puntos_temp_c)
ruido_amb = np.random.normal(0, 0.5, size=num_puntos)
t_amb = t_amb_c + ruido_amb + 273.15

df = pd.DataFrame({
    'timestamp': [datetime(2023, 1, 1) + timedelta(seconds=s) for s in t_seg],
    'POA': poa,
    'T_amb': t_amb,
})

df.to_csv('datos_meteorologicos_sinteticos.csv', index=False, float_format='%.2f')

print(f"Generados {len(df)} registros.")
print(df.head(10))
print("\nEstadísticas:")
print(df[['POA', 'T_amb']].describe())
