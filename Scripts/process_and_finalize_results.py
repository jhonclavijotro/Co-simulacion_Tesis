#!/usr/bin/env python3
"""
Procesamiento de Métricas y Finalización de Ensayos para S-O-42 y S-O-43.
"""

import os
import sys
import json
import shutil
import subprocess
import time
import pandas as pd
import numpy as np

WORKSPACE = r"D:\Antigravity\Projects\Tesis_Grado"
BASE_SCENARIOS = os.path.join(WORKSPACE, "Forms", "escenarios_generados")
ACTIVO_TXT = os.path.join(BASE_SCENARIOS, "ACTIVO.txt")
SRC_SCENARIO = os.path.join(BASE_SCENARIOS, "ESC-HIL-016_excitacion_reactiva_180s")
PYTHON_EXE = os.path.join(WORKSPACE, ".venv", "Scripts", "python.exe")
RESULTS_DIR = os.path.join(WORKSPACE, "outputs", "custom", "results")
CANONICAL_BASELINE = "ESC-HIL-008_validacion_integrada"

def get_latest_run(scenario_prefix):
    candidates = [os.path.join(RESULTS_DIR, d) for d in os.listdir(RESULTS_DIR) if scenario_prefix in d]
    candidates.sort(key=os.path.getmtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No run found for {scenario_prefix}")
    return candidates[0]

def create_scenario(name, consensus_interval=0.5, c1=None, c2=None, q_step2=None, duracion_s=180):
    dest = os.path.join(BASE_SCENARIOS, name)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(SRC_SCENARIO, dest)
    
    meta_path = os.path.join(dest, "meta.json")
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
        
    meta["id"] = name.split("_")[0]
    meta["duracion_s"] = duracion_s
    meta["consensus_interval"] = consensus_interval
    meta["T_c"] = consensus_interval
    if c1 is not None and c2 is not None:
        meta["c1"] = c1
        meta["c2"] = c2
    if q_step2 is not None:
        meta["excitacion_reactiva_2"] = q_step2
        
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"[OK] Escenario creado: {name} (Tc={consensus_interval}s, c1={c1}, c2={c2})")
    return dest

def run_scenario(name, steps=241):
    with open(ACTIVO_TXT, "w", encoding="utf-8") as f:
        f.write(name)
        
    cmd = [
        PYTHON_EXE, "-u", "-B", "Scripts/run_rack_experiment_orchestrator.py",
        "--campaign", "custom",
        "--scenario", name,
        "--steps", str(steps),
        "--local-sil",
        "--fast"
    ]
    print(f"\n>>> Ejecutando {name} ({steps} pasos / {steps*0.5 - 0.5:.1f} s)...")
    t0 = time.time()
    res = subprocess.run(cmd, cwd=WORKSPACE, capture_output=True, text=True)
    elap = time.time() - t0
    if res.returncode != 0:
        print(f"[ERROR] Fallo en la ejecucion de {name}:")
        print(res.stderr[-500:])
        raise RuntimeError(f"Fallo al ejecutar {name}")
    print(f"[OK] Completado {name} en {elap:.1f} s.")
    return get_latest_run(name)

def analyze_telemetry_file(csv_path, tc_val, open_loop_ref=0.43477):
    df = pd.read_csv(csv_path)
    
    # Ratios normalizados
    df["q1"] = df["Q1_kvar"] / 6.0
    df["q2"] = df["Q2_kvar"] / 3.0
    df["q3"] = df["Q3_kvar"] / 1.0
    df["disp_exact"] = df[["q1", "q2", "q3"]].max(axis=1) - df[["q1", "q2", "q3"]].min(axis=1)
    
    # Cola de ultimos 30 s: [150, 180] s
    cola = df[(df["time_s"] >= 150.0) & (df["time_s"] <= 180.0)]
    disp_media = cola["disp_exact"].mean()
    disp_max = cola["disp_exact"].max()
    disp_min = cola["disp_exact"].min()
    p2p_disp = disp_max - disp_min
    
    factor_reduccion = open_loop_ref / disp_media if disp_media > 0 else np.nan
    tf_efectivo = 52.54 * (tc_val / 0.5)
    
    f_cola = cola["f_sys_hz"]
    p2p_f = f_cola.max() - f_cola.min()
    f_estable = p2p_f <= 0.10
    
    # Calculo robusto del indice de chattering sobre los pasos donde actualiza consenso
    # Para N2 (Solar): droop local m_q2 = 8.0 / 3000 = 0.0026667
    m_q2 = 8.0 / 3000.0
    q_droop_2 = (400.0 - df["V2_V"]) / m_q2
    delta_Q_sec2 = df["Q2_kvar"] * 1000.0 - q_droop_2
    
    # Filtrar solo pasos de actualizacion (cada Tc / 0.5 pasos)
    interval_steps = max(1, int(round(tc_val / 0.5)))
    df_updates = delta_Q_sec2.iloc[::interval_steps]
    dQ_updates = df_updates.diff().dropna()
    
    # Signo con tolerancia numerica
    signs = np.sign(np.where(np.abs(dQ_updates) < 0.05, 0.0, dQ_updates))
    signs_nonzero = signs[signs != 0]
    if len(signs_nonzero) > 1:
        sign_changes = (signs_nonzero[1:] != signs_nonzero[:-1]).sum()
        chattering_idx = float(sign_changes / (len(signs_nonzero) - 1))
    else:
        chattering_idx = 0.0
        
    return {
        "disp_media": disp_media,
        "disp_max": disp_max,
        "disp_min": disp_min,
        "p2p_disp": p2p_disp,
        "factor_reduccion": factor_reduccion,
        "tf_efectivo": tf_efectivo,
        "p2p_f": p2p_f,
        "f_estable": f_estable,
        "chattering_idx_n2": chattering_idx
    }

def main():
    print("=== FINALIZANDO ENSAYOS Y PROCESANDO MÉTRICAS S-O-42 Y S-O-43 ===")
    
    # 1. Medición de tau_droop sobre ESC-HIL-019
    run_019 = get_latest_run("ESC-HIL-019")
    df_019 = pd.read_csv(os.path.join(run_019, "telemetry_rack.csv"))
    df_019["q1"] = df_019["Q1_kvar"] / 6.0
    df_019["q2"] = df_019["Q2_kvar"] / 3.0
    df_019["q3"] = df_019["Q3_kvar"] / 1.0
    df_019["disp"] = df_019[["q1", "q2", "q3"]].max(axis=1) - df_019[["q1", "q2", "q3"]].min(axis=1)
    
    tau_droop_dict = {}
    for col, name in [("Q1_kvar", "N1"), ("Q2_kvar", "N2"), ("Q3_kvar", "N3"), ("disp", "Agregado_disp")]:
        y0 = df_019[(df_019["time_s"] >= 45.0) & (df_019["time_s"] < 50.0)][col].mean()
        y_post = df_019[(df_019["time_s"] >= 50.5) & (df_019["time_s"] <= 54.5)][col].mean()
        dy = y_post - y0
        post_df = df_019[df_019["time_s"] >= 50.0]
        t63 = post_df[np.abs(post_df[col] - y0) >= 0.632 * np.abs(dy)]["time_s"].iloc[0]
        t95 = post_df[np.abs(post_df[col] - y0) >= 0.950 * np.abs(dy)]["time_s"].iloc[0]
        tau_droop_dict[name] = {
            "y0": float(y0), "y_post": float(y_post), "dy": float(dy),
            "tau_63": float(t63 - 50.0), "tau_95": float(t95 - 50.0)
        }
    print("\n--- T1-P2: MEDIDA DE tau_droop SOBRE ESC-HIL-019 ---")
    for k, v in tau_droop_dict.items():
        print(f"  {k}: y0={v['y0']:.4f}, post={v['y_post']:.4f}, dy={v['dy']:+.4f} | tau_63={v['tau_63']:.3f}s, tau_95={v['tau_95']:.3f}s")
    tau_droop_efectivo = 0.50

    # 2. Analizar las corridas de barrido A, B, C, D y B'
    casos = {
        "Caso A": {"prefix": "ESC-HIL-020A", "Tc": 0.5, "c1": 0.25, "c2": 0.15},
        "Caso B": {"prefix": "ESC-HIL-020B", "Tc": 1.0, "c1": 0.25, "c2": 0.15},
        "Caso C / A'": {"prefix": "ESC-HIL-020C", "Tc": 2.0, "c1": 0.25, "c2": 0.15},
        "Caso D": {"prefix": "ESC-HIL-020D", "Tc": 5.0, "c1": 0.25, "c2": 0.15},
        "Corrida B'": {"prefix": "ESC-HIL-021", "Tc": 0.5, "c1": 0.0625, "c2": 0.0375},
    }
    
    barrido_res = {}
    for tag, cfg in casos.items():
        r_dir = get_latest_run(cfg["prefix"])
        m = analyze_telemetry_file(os.path.join(r_dir, "telemetry_rack.csv"), tc_val=cfg["Tc"])
        m["Tc/tau_droop"] = cfg["Tc"] / tau_droop_efectivo
        barrido_res[tag] = {
            "cfg": cfg,
            "run_dir": r_dir,
            "metrics": m
        }

    print("\n--- RESUMEN BARRIDO S-O-42 Y CONTROL DE GANANCIA T1-P1 ---")
    rows = []
    for tag, d in barrido_res.items():
        m = d["metrics"]
        rows.append({
            "Caso": tag,
            "Tc [s]": d["cfg"]["Tc"],
            "Sub-pasos droop": int(round(d["cfg"]["Tc"] / 0.5)),
            "Tc/tau_droop": m["Tc/tau_droop"],
            "Disp. Media": f"{m['disp_media']:.5f}",
            "Disp. Max": f"{m['disp_max']:.5f}",
            "p2p Residuo": f"{m['p2p_disp']:.5f}",
            "Factor Reduccion": f"{m['factor_reduccion']:.2f}x",
            "Tf efectivo [s]": f"{m['tf_efectivo']:.1f}",
            "p2p Frec [Hz]": f"{m['p2p_f']:.4f}",
            "Chattering N2": f"{m['chattering_idx_n2']:.4f}"
        })
    df_summary = pd.DataFrame(rows)
    print(df_summary.to_string(index=False))

    # 3. T2-P4: Predicción a priori para Tc = 3.0 s y contrastación
    tc_p4 = [0.5, 1.0, 2.0, 5.0]
    p2p_p4 = [
        barrido_res["Caso A"]["metrics"]["p2p_disp"],
        barrido_res["Caso B"]["metrics"]["p2p_disp"],
        barrido_res["Caso C / A'"]["metrics"]["p2p_disp"],
        barrido_res["Caso D"]["metrics"]["p2p_disp"]
    ]
    mean_disp_p4 = [
        barrido_res["Caso A"]["metrics"]["disp_media"],
        barrido_res["Caso B"]["metrics"]["disp_media"],
        barrido_res["Caso C / A'"]["metrics"]["disp_media"],
        barrido_res["Caso D"]["metrics"]["disp_media"]
    ]
    
    log_x = np.log(np.array(tc_p4) / tau_droop_efectivo)
    log_y_p2p = np.log(p2p_p4)
    log_y_mean = np.log(mean_disp_p4)
    
    slope_p2p, intercept_p2p = np.polyfit(log_x, log_y_p2p, 1)
    slope_mean, intercept_mean = np.polyfit(log_x, log_y_mean, 1)
    
    x_pred = 3.0 / tau_droop_efectivo
    pred_p2p = float(np.exp(intercept_p2p + slope_p2p * np.log(x_pred)))
    pred_mean = float(np.exp(intercept_mean + slope_mean * np.log(x_pred)))
    
    r_dir_tc3 = get_latest_run("ESC-HIL-022")
    m_tc3 = analyze_telemetry_file(os.path.join(r_dir_tc3, "telemetry_rack.csv"), tc_val=3.0)
    m_tc3["Tc/tau_droop"] = 3.0 / tau_droop_efectivo
    
    err_p2p = float((m_tc3["p2p_disp"] - pred_p2p) / pred_p2p * 100.0)
    err_mean = float((m_tc3["disp_media"] - pred_mean) / pred_mean * 100.0)
    valida_p4 = abs(err_p2p) <= 20.0 and abs(err_mean) <= 20.0
    
    print("\n--- T2-P4: PREDICCIÓN FUERA DE MUESTRA (Tc = 3.0 s) ---")
    print(f"  Modelo p2p: residuo_p2p = exp({intercept_p2p:.4f}) * (Tc/tau)^{slope_p2p:.4f}")
    print(f"  Prediccion p2p = {pred_p2p:.5f} (Banda +-20%: [{pred_p2p*0.8:.5f}, {pred_p2p*1.2:.5f}])")
    print(f"  Medido p2p     = {m_tc3['p2p_disp']:.5f} (Error: {err_p2p:+.2f}%)")
    print(f"  Prediccion media = {pred_mean:.5f} (Banda +-20%: [{pred_mean*0.8:.5f}, {pred_mean*1.2:.5f}])")
    print(f"  Medido media     = {m_tc3['disp_media']:.5f} (Error: {err_mean:+.2f}%)")
    print(f"  Dictamen T2-P4: {'EXITOSO (Dentro de +-20%)' if valida_p4 else 'REPROBADO'}")

    # 4. T2-P5: Costo de la Ventana Amplia (Latencia ante segundo escalón a Tc/2)
    print("\n--- T2-P5: COSTO DE LA VENTANA AMPLIA ---")
    # Ejecutar 023B (Tc=2.0s) y 023C (Tc=5.0s) si no existen
    latencia_tests = [
        {"name": "ESC-HIL-023A_latencia_Tc_05s", "Tc": 0.5, "t_step": 90.0},
        {"name": "ESC-HIL-023B_latencia_Tc_20s", "Tc": 2.0, "t_step": 91.0},
        {"name": "ESC-HIL-023C_latencia_Tc_50s", "Tc": 5.0, "t_step": 92.5},
    ]
    lat_results = {}
    for cfg_l in latencia_tests:
        n = cfg_l["name"]
        try:
            r_dir_l = get_latest_run(n)
        except FileNotFoundError:
            q_step2_cfg = {"nodo": 5, "q_step_var": 1000.0, "inicio_s": cfg_l["t_step"], "duracion_s": 5.0}
            create_scenario(n, consensus_interval=cfg_l["Tc"], q_step2=q_step2_cfg, duracion_s=120)
            r_dir_l = run_scenario(n, steps=241)
            
        # Analizar latencia desde telemetry_rack.csv
        df_l = pd.read_csv(os.path.join(r_dir_l, "telemetry_rack.csv"))
        m_q2 = 8.0 / 3000.0
        q_droop_2 = (400.0 - df_l["V2_V"]) / m_q2
        df_l["delta_Q_sec2"] = df_l["Q2_kvar"] * 1000.0 - q_droop_2
        
        # Valor de delta_Q_sec2 justo antes del escalon
        pre_val = df_l[df_l["time_s"] < cfg_l["t_step"]]["delta_Q_sec2"].iloc[-1]
        post_df = df_l[df_l["time_s"] >= cfg_l["t_step"]]
        
        # Primer paso donde delta_Q_sec2 se mueve por accion secundaria del consenso
        # Umbral: cambio significativo (> 0.5 var)
        react_steps = post_df[np.abs(post_df["delta_Q_sec2"] - pre_val) > 0.5]
        if len(react_steps) > 0:
            t_react = float(react_steps["time_s"].iloc[0])
            latencia = float(t_react - cfg_l["t_step"])
        else:
            t_react = np.nan
            latencia = np.nan
            
        lat_results[cfg_l["name"]] = {
            "Tc": cfg_l["Tc"],
            "t_step": cfg_l["t_step"],
            "t_react": t_react,
            "latencia_s": latencia
        }
        print(f"  {n}: Tc={cfg_l['Tc']}s | Escalon a t={cfg_l['t_step']:.1f}s -> Reaccion consenso a t={t_react:.1f}s | Latencia = {latencia:.2f} s")

    # Consolidar JSON final
    out_all = {
        "tau_droop": tau_droop_dict,
        "barrido_s42": {k: {"cfg": v["cfg"], "metrics": v["metrics"]} for k, v in barrido_res.items()},
        "prediccion_p4": {
            "pred_p2p": pred_p2p, "pred_mean": pred_mean,
            "medido_p2p": m_tc3["p2p_disp"], "medido_mean": m_tc3["disp_media"],
            "error_p2p_pct": err_p2p, "error_mean_pct": err_mean,
            "valida": valida_p4
        },
        "latencia_p5": lat_results
    }
    with open(os.path.join(WORKSPACE, "outputs", "custom", "resultados_so42_so43.json"), "w", encoding="utf-8") as f:
        json.dump(out_all, f, indent=2, default=str)
    print("\n[OK] Resultados finales guardados en outputs/custom/resultados_so42_so43.json")

    # Restaurar ACTIVO.txt
    with open(ACTIVO_TXT, "w", encoding="utf-8") as f:
        f.write(CANONICAL_BASELINE)
    print(f"[OK] ACTIVO.txt restaurado a {CANONICAL_BASELINE}.")

if __name__ == "__main__":
    main()
