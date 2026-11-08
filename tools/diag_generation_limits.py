import sys, os
sys.path.insert(0, os.path.abspath("."))
import math
import pandas as pd
import numpy as np

from Agents.node_dynamic_process import NodeDynamicProcess
from Agents.finite_time_consensus import FixedTimeConsensusAgent

print("=" * 60)
print("DIAGNOSTICO DINAMICO DE DIESEL, BESS Y SOLAR TRAS ESCALON t=180s")
print("=" * 60)

# 1. Cargar demandas y radiacion
df_a = pd.read_csv('Forms/escenarios_generados/ESC-HIL-001_rampa_sombreado_demanda/datos_demanda_A.csv')
df_b = pd.read_csv('Forms/escenarios_generados/ESC-HIL-001_rampa_sombreado_demanda/datos_demanda_B.csv')
df_c = pd.read_csv('Forms/escenarios_generados/ESC-HIL-001_rampa_sombreado_demanda/datos_demanda_C.csv')
df_d = pd.read_csv('Forms/escenarios_generados/ESC-HIL-001_rampa_sombreado_demanda/datos_demanda_D.csv')
df_e = pd.read_csv('Forms/escenarios_generados/ESC-HIL-001_rampa_sombreado_demanda/datos_demanda_E.csv')

total_p_load = (df_a['P_kW'] + df_b['P_kW'] + df_c['P_kW'] + df_d['P_kW'] + df_e['P_kW']).values * 1000.0

print(f"Demanda total a t=100s (paso 200): {total_p_load[200]:.1f} W")
print(f"Demanda total a t=180s (paso 360): {total_p_load[360]:.1f} W")
print(f"Demanda total a t=200s (paso 400): {total_p_load[400]:.1f} W")
print(f"Demanda total a t=240s (paso 480): {total_p_load[480]:.1f} W")
print(f"Incremento neto de carga: {total_p_load[480] - total_p_load[200]:.1f} W")

# 2. Verificar capacidades fisicas de DERs
# Diesel: p_max=12000 W
# BESS: p_max=1500 W
# Solar: p_max=5000 W
proc_solar = NodeDynamicProcess(node_id=2, source_type="SOLAR", hold_mode="ZOH")
proc_diesel = NodeDynamicProcess(node_id=1, source_type="DIESEL", hold_mode="ZOH")
proc_bess = NodeDynamicProcess(node_id=3, source_type="BESS", hold_mode="ZOH")

# Estado de generacion solar a t=180s (paso 360)
proc_solar.step_index = 360
out_solar = proc_solar.step_macro(V_pcc=400.0, Q_ref=0.0, P_ref=2000.0, delta_omega=0.0)
print(f"\nSolar P_w a paso 360: {out_solar['P_w']:.1f} W")

# Diesel con P_ref = 10000 W
out_diesel_10k = proc_diesel.step_macro(V_pcc=400.0, Q_ref=0.0, P_ref=10000.0, delta_omega=0.0)
print(f"Diesel P_w con P_ref=10000 W: {out_diesel_10k['P_w']:.1f} W")

# Diesel con P_ref = 12000 W
out_diesel_12k = proc_diesel.step_macro(V_pcc=400.0, Q_ref=0.0, P_ref=12000.0, delta_omega=0.0)
print(f"Diesel P_w con P_ref=12000 W: {out_diesel_12k['P_w']:.1f} W")

# BESS con P_ref = 1500 W
out_bess_1500 = proc_bess.step_macro(V_pcc=400.0, Q_ref=0.0, P_ref=1500.0, delta_omega=0.0)
print(f"BESS P_w con P_ref=1500 W: {out_bess_1500['P_w']:.1f} W")
