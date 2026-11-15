import pandas as pd
import numpy as np

csv_path = "output_data/telemetry_monitor_cluster_8nodes_hil.csv"
df = pd.read_csv(csv_path)

print("=" * 60)
print("ANALISIS DETALLADO DEL EXPERIMENTO HIL (600 PASOS / 300 S)")
print("=" * 60)
print(f"Columnas ({len(df.columns)}):", list(df.columns))
print(f"Total registros: {len(df)}")
t_min, t_max = df["time_sec"].min(), df["time_sec"].max()
print(f"Rango temporal: [{t_min:.1f}, {t_max:.1f}] s")

print("\n--- METRICAS DE FRECUENCIA (f_sys_hz) ---")
idx_min = df["f_sys_hz"].idxmin()
idx_max = df["f_sys_hz"].idxmax()
print(f"Frecuencia Minima: {df.loc[idx_min, 'f_sys_hz']:.4f} Hz (t = {df.loc[idx_min, 'time_sec']:.1f} s, step = {df.loc[idx_min, 'step']})")
print(f"Frecuencia Maxima: {df.loc[idx_max, 'f_sys_hz']:.4f} Hz (t = {df.loc[idx_max, 'time_sec']:.1f} s, step = {df.loc[idx_max, 'step']})")
print(f"Frecuencia Promedio: {df['f_sys_hz'].mean():.4f} Hz")
print(f"Desviacion Estandar: {df['f_sys_hz'].std():.4f} Hz")

print("\n--- EVOLUCION TEMPORAL (Muestras cada 20 segundos) ---")
for t in range(0, int(t_max) + 1, 20):
    sub = df[df["time_sec"] >= t].iloc[0]
    p_net = sub.get("P_net_kW", np.nan)
    v1 = sub.get("V1_pu", np.nan)
    v8 = sub.get("V8_pu", np.nan)
    f = sub.get("f_sys_hz", np.nan)
    print(f"t={sub['time_sec']:5.1f} s | f={f:6.3f} Hz | P_net={p_net:6.2f} kW | V1={v1:.4f} pu | V8={v8:.4f} pu")

print("\n--- ANALISIS DE LA TRANSICION EN TORNO A t = 180 s - 240 s ---")
trans = df[(df["time_sec"] >= 170.0) & (df["time_sec"] <= 240.0)]
for _, row in trans.iloc[::4].iterrows():
    p_net = row.get("P_net_kW", np.nan)
    f = row.get("f_sys_hz", np.nan)
    p1 = row.get("P1_W", np.nan)
    p2 = row.get("P2_W", np.nan)
    p3 = row.get("P3_W", np.nan)
    print(f"t={row['time_sec']:5.1f} s (step {int(row['step']):3d}) | f={f:6.3f} Hz | P_net={p_net:6.2f} kW | P1={p1} | P2={p2} | P3={p3}")

print("\n--- DERs POTENCIAS (Si estan en CSV) ---")
der_cols = [c for c in df.columns if any(k in c for k in ["P1", "P2", "P3", "P_ratio", "eta", "der", "diesel", "solar", "bess"])]
print("Columnas de DERs detectadas:", der_cols)
if der_cols:
    print(df[der_cols].describe())

