import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Parámetros
duracion_horas = 24
frecuencia_seg = 0.5  # 500 ms
num_puntos = int(duracion_horas * 3600 / frecuencia_seg)

# 1. Crear línea de tiempo
t_seg = np.arange(0, duracion_horas * 3600, frecuencia_seg)  # segundos desde 00:00
hora = t_seg / 3600.0  # horas del día (0 a 24)

# 2. Radiación POA (perfil gaussiano)
sigma_poa = 3.0  # horas, para que a las 6 y 18 sea ~115 W/m²
poa_media = 12.0
poa_max = 850.0
poa_sin_ruido = poa_max * np.exp(-0.5 * ((hora - poa_media) / sigma_poa) ** 2)
# Solo entre 6 y 18
poa_sin_ruido = np.where((hora >= 6) & (hora <= 18), poa_sin_ruido, 0.0)
# Añadir ruido gaussiano (sigma = 5 W/m²)
ruido_poa = np.random.normal(0, 5, size=num_puntos)
poa = poa_sin_ruido + ruido_poa
poa = np.maximum(poa, 0)  # sin valores negativos

# 3. Temperatura ambiente (interpolación lineal)
puntos_hora = [0, 6, 10, 14, 18, 24]
puntos_temp = [20, 26, 26, 32, 24, 20]  # °C
t_amb_sin_ruido = np.interp(hora, puntos_hora, puntos_temp)
ruido_amb = np.random.normal(0, 0.5, size=num_puntos)
t_amb = t_amb_sin_ruido + ruido_amb

# 4. Temperatura de panel (función cuadrática entre 6 y 18)
# Polinomio que pasa por (6,26), (12,60), (18,24)
a = -0.9722222222
b = 23.1666666667
c = -78.0
t_panel_sin_ruido = a * hora**2 + b * hora + c
# Fuera de 6-18 se fija en el valor del borde (26 a las 6, 24 a las 18)
t_panel_sin_ruido = np.where((hora >= 6) & (hora <= 18), t_panel_sin_ruido,
                             np.where(hora < 6, 26, 24))
# Añadir ruido
ruido_panel = np.random.normal(0, 0.5, size=num_puntos)
t_panel = t_panel_sin_ruido + ruido_panel

# 5. Construir DataFrame
df = pd.DataFrame({
    'timestamp': [datetime(2023, 1, 1) + timedelta(seconds=s) for s in t_seg],
    'POA': poa,
    'T_amb': t_amb,
    'T_panel': t_panel
})

# 6. Guardar a CSV (opcional)
df.to_csv('datos_meteorologicos_sinteticos.csv', index=False, float_format='%.2f')

# 7. Mostrar un resumen
print(f"Generados {len(df)} registros.")
print(df.head(10))
print("\nEstadísticas:")
print(df[['POA', 'T_amb', 'T_panel']].describe())