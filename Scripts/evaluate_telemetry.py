import pandas as pd

df = pd.read_csv("output_data/telemetry_monitor_cluster_rpi.csv")
f = df["f_sys_hz"]
p = df["P_net_kW"]

print(f"Total registros: {len(df)}")
print(f"Frecuencia Min:  {f.min():.4f} Hz")
print(f"Frecuencia Mean: {f.mean():.4f} Hz")
print(f"Frecuencia Max:  {f.max():.4f} Hz")

ntc_mask = (f >= 58.8) & (f <= 61.2)
pct_ntc = (ntc_mask.sum() / len(f)) * 100.0
print(f"Cumplimiento NTC 1340: {pct_ntc:.2f}%")
print(f"P_net Min:  {p.min():.3f} kW")
print(f"P_net Mean: {p.mean():.3f} kW")
print(f"P_net Max:  {p.max():.3f} kW")
print(f"Q_ratio final (N1, N2, N3): ({df['Q_ratio_1'].iloc[-1]:.4f}, {df['Q_ratio_2'].iloc[-1]:.4f}, {df['Q_ratio_3'].iloc[-1]:.4f})")
print(f"Error Q_12 final: {df['error_Q_12'].iloc[-1]:.5f}")
print(f"Error Q_23 final: {df['error_Q_23'].iloc[-1]:.5f}")
v_cols = [c for c in df.columns if c.startswith("V") and c.endswith("_pu")]
print(f"Tensión Min: {df[v_cols].min().min():.4f} pu")
print(f"Tensión Max: {df[v_cols].max().max():.4f} pu")
