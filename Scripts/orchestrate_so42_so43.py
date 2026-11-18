#!/usr/bin/env python3
"""
Orquestador Integral de Ensayos SIL y Análisis para S-O-42 y S-O-43.
"""

import os
import sys
import json
import shutil
import subprocess
import time
import math
import pandas as pd
import numpy as np

WORKSPACE = r"D:\Antigravity\Projects\Tesis_Grado"
BASE_SCENARIOS = os.path.join(WORKSPACE, "Forms", "escenarios_generados")
ACTIVO_TXT = os.path.join(BASE_SCENARIOS, "ACTIVO.txt")
SRC_SCENARIO = os.path.join(BASE_SCENARIOS, "ESC-HIL-016_excitacion_reactiva_180s")
PYTHON_EXE = os.path.join(WORKSPACE, ".venv", "Scripts", "python.exe")
CANONICAL_BASELINE = "ESC-HIL-008_validacion_integrada"

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

def run_scenario(name, steps=361):
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
    
    results_dir = os.path.join(WORKSPACE, "outputs", "custom", "results")
    candidates = [os.path.join(results_dir, d) for d in os.listdir(results_dir) if name in d]
    candidates.sort(key=os.path.getmtime, reverse=True)
    latest_run = candidates[0]
    
    for n_id in (1, 2, 3):
        uq_src = os.path.join(WORKSPACE, "output_data", f"node_{n_id}_uq.csv")
        if os.path.exists(uq_src):
            shutil.copy2(uq_src, os.path.join(latest_run, f"node_{n_id}_uq.csv"))
            
    return latest_run

def analyze_telemetry(run_dir, tc_val, open_loop_ref=0.43477):
    csv_path = os.path.join(run_dir, "telemetry_rack.csv")
    df = pd.read_csv(csv_path)
    
    # Calcular dispersion exacta de los 3 DERs
    df["q1"] = df["Q1_kvar"] / 6.0
    df["q2"] = df["Q2_kvar"] / 3.0
    df["q3"] = df["Q3_kvar"] / 1.0
    df["disp_exact"] = df[["q1", "q2", "q3"]].max(axis=1) - df[["q1", "q2", "q3"]].min(axis=1)
    
    # Cola de los ultimos 30 s: [150.0, 180.0] s
    cola = df[(df["time_s"] >= 150.0) & (df["time_s"] <= 180.0)]
    
    disp_media = cola["disp_exact"].mean()
    disp_max = cola["disp_exact"].max()
    disp_min = cola["disp_exact"].min()
    p2p_disp = disp_max - disp_min
    
    # Factor de reduccion frente a lazo abierto (019: 0.43477)
    factor_reduccion = open_loop_ref / disp_media if disp_media > 0 else np.nan
    
    # Tf efectivo: escala con Tc / 0.5 (cota analitica Polyakov discreta)
    tf_efectivo = 52.54 * (tc_val / 0.5)
    
    # Estabilidad
    f_cola = cola["f_sys_hz"]
    p2p_f = f_cola.max() - f_cola.min()
    f_estable = p2p_f <= 0.10
    
    # Indice de chattering desde los archivos de nodo
    chattering_indices = {}
    for n_id in (1, 2, 3):
        uq_file = os.path.join(run_dir, f"node_{n_id}_uq.csv")
        if not os.path.exists(uq_file):
            uq_fallback = os.path.join(WORKSPACE, "output_data", f"node_{n_id}_uq.csv")
            if os.path.exists(uq_fallback):
                uq_file = uq_fallback
        if os.path.exists(uq_file):
            try:
                df_uq = pd.read_csv(uq_file)
                u_vals = df_uq["u_q"].values
                n_updates = len(u_vals)
                if n_updates > 1:
                    # Signo con umbral numerico
                    signs = np.sign(np.where(np.abs(u_vals) < 1e-9, 0.0, u_vals))
                    sign_changes = sum(1 for k in range(1, n_updates) if signs[k] != 0 and signs[k-1] != 0 and signs[k] != signs[k-1])
                    chattering_indices[f"node_{n_id}"] = sign_changes / (n_updates - 1)
                else:
                    chattering_indices[f"node_{n_id}"] = 0.0
            except Exception:
                chattering_indices[f"node_{n_id}"] = np.nan
        else:
            chattering_indices[f"node_{n_id}"] = np.nan
            
    avg_chattering = np.nanmean(list(chattering_indices.values())) if any(not np.isnan(v) for v in chattering_indices.values()) else np.nan
    
    return {
        "disp_media": disp_media,
        "disp_max": disp_max,
        "disp_min": disp_min,
        "p2p_disp": p2p_disp,
        "factor_reduccion": factor_reduccion,
        "tf_efectivo": tf_efectivo,
        "p2p_f": p2p_f,
        "f_estable": f_estable,
        "chattering": chattering_indices,
        "avg_chattering": avg_chattering
    }

def main():
    print("=== INICIANDO EXPERIMENTACION FORMAL S-O-42 Y S-O-43 ===")
    
    # T1-P2: Medir tau_droop sobre la corrida 019
    path_019 = os.path.join(WORKSPACE, "outputs", "custom", "results", "20261118T102916_ESC-HIL-019_diagnostico_consenso_congelado_60s_seed42", "telemetry_rack.csv")
    df_019 = pd.read_csv(path_019)
    df_019["q1"] = df_019["Q1_kvar"] / 6.0
    df_019["q2"] = df_019["Q2_kvar"] / 3.0
    df_019["q3"] = df_019["Q3_kvar"] / 1.0
    df_019["disp"] = df_019[["q1", "q2", "q3"]].max(axis=1) - df_019[["q1", "q2", "q3"]].min(axis=1)
    
    tau_droop_dict = {}
    for col, name in [("Q1_kvar", "N1"), ("Q2_kvar", "N2"), ("Q3_kvar", "N3"), ("disp", "Agregado_disp")]:
        y0 = df_019[(df_019["time_s"] >= 45.0) & (df_019["time_s"] < 50.0)][col].mean()
        y_post = df_019[(df_019["time_s"] >= 50.5) & (df_019["time_s"] <= 54.5)][col].mean()
        dy = y_post - y0
        # Primer paso >= 50.0 que cruza 63% y 95%
        post_df = df_019[df_019["time_s"] >= 50.0]
        t63 = post_df[np.abs(post_df[col] - y0) >= 0.632 * np.abs(dy)]["time_s"].iloc[0]
        t95 = post_df[np.abs(post_df[col] - y0) >= 0.950 * np.abs(dy)]["time_s"].iloc[0]
        tau_droop_dict[name] = {
            "y0": y0, "y_post": y_post, "dy": dy,
            "tau_63": t63 - 50.0, "tau_95": t95 - 50.0
        }
    print("\n--- RESULTADOS T1-P2: MEDIDA DE tau_droop SOBRE ESC-HIL-019 ---")
    for k, v in tau_droop_dict.items():
        print(f"  {k}: y0={v['y0']:.4f}, post={v['y_post']:.4f}, dy={v['dy']:+.4f} | tau_63={v['tau_63']:.3f}s, tau_95={v['tau_95']:.3f}s")
        
    tau_droop_efectivo = 0.50  # Resolucion del paso macro del lazo primario
    
    # 1. Definicion de Casos para el Barrido S-O-42 y T1-P1
    casos = {
        "Caso A": {"name": "ESC-HIL-020A_separacion_escalas_Tc_05s", "Tc": 0.5, "c1": None, "c2": None},
        "Caso B": {"name": "ESC-HIL-020B_separacion_escalas_Tc_10s", "Tc": 1.0, "c1": None, "c2": None},
        "Caso C / A'": {"name": "ESC-HIL-020C_separacion_escalas_Tc_20s", "Tc": 2.0, "c1": None, "c2": None},
        "Caso D": {"name": "ESC-HIL-020D_separacion_escalas_Tc_50s", "Tc": 5.0, "c1": None, "c2": None},
        "Corrida B'": {"name": "ESC-HIL-021_control_ganancia_Tc_05s_div4", "Tc": 0.5, "c1": 0.0625, "c2": 0.0375},
    }
    
    runs_results = {}
    for tag, cfg in casos.items():
        print(f"\n==========================================")
        print(f"  Procesando: {tag} -> {cfg['name']}")
        print(f"==========================================")
        create_scenario(cfg["name"], consensus_interval=cfg["Tc"], c1=cfg["c1"], c2=cfg["c2"])
        run_dir = run_scenario(cfg["name"], steps=361)
        metrics = analyze_telemetry(run_dir, tc_val=cfg["Tc"])
        metrics["Tc/tau_droop"] = cfg["Tc"] / tau_droop_efectivo
        runs_results[tag] = {
            "cfg": cfg,
            "run_dir": run_dir,
            "metrics": metrics
        }
        
    print("\n--- RESUMEN BARRIDO S-O-42 Y CONTROL DE GANANCIA T1-P1 ---")
    summary_rows = []
    for tag, data in runs_results.items():
        m = data["metrics"]
        summary_rows.append({
            "Caso": tag,
            "Tc [s]": data["cfg"]["Tc"],
            "Sub-pasos droop": int(round(data["cfg"]["Tc"] / 0.5)),
            "Tc/tau_droop": m["Tc/tau_droop"],
            "Disp. Media": f"{m['disp_media']:.5f}",
            "Disp. Max": f"{m['disp_max']:.5f}",
            "p2p Residuo": f"{m['p2p_disp']:.5f}",
            "Factor Reduccion": f"{m['factor_reduccion']:.2f}x",
            "Tf efectivo [s]": f"{m['tf_efectivo']:.1f}",
            "p2p Frec [Hz]": f"{m['p2p_f']:.4f}",
            "Chattering N1": f"{m['chattering'].get('node_1', np.nan):.3f}",
            "Chattering N2": f"{m['chattering'].get('node_2', np.nan):.3f}",
            "Chattering N3": f"{m['chattering'].get('node_3', np.nan):.3f}",
            "Chattering Prom": f"{m['avg_chattering']:.3f}"
        })
    df_summary = pd.DataFrame(summary_rows)
    print(df_summary.to_string(index=False))
    
    # 2. T2-P4: Prediccion Fuera de Muestra para Tc = 3.0 s
    print("\n--- T2-P4: AJUSTE Y PREDICCIÓN FUERA DE MUESTRA PARA Tc = 3.0 s ---")
    tc_p4 = [0.5, 1.0, 2.0, 5.0]
    p2p_p4 = [
        runs_results["Caso A"]["metrics"]["p2p_disp"],
        runs_results["Caso B"]["metrics"]["p2p_disp"],
        runs_results["Caso C / A'"]["metrics"]["p2p_disp"],
        runs_results["Caso D"]["metrics"]["p2p_disp"]
    ]
    mean_disp_p4 = [
        runs_results["Caso A"]["metrics"]["disp_media"],
        runs_results["Caso B"]["metrics"]["disp_media"],
        runs_results["Caso C / A'"]["metrics"]["disp_media"],
        runs_results["Caso D"]["metrics"]["disp_media"]
    ]
    
    # Ajuste por ley de potencia / modelo inverso residuo vs (Tc / tau_droop)
    # y = a * x^b o regresion log-log
    log_x = np.log(np.array(tc_p4) / tau_droop_efectivo)
    log_y_p2p = np.log(p2p_p4)
    log_y_mean = np.log(mean_disp_p4)
    
    slope_p2p, intercept_p2p = np.polyfit(log_x, log_y_p2p, 1)
    slope_mean, intercept_mean = np.polyfit(log_x, log_y_mean, 1)
    
    x_pred = 3.0 / tau_droop_efectivo
    pred_p2p = np.exp(intercept_p2p + slope_p2p * np.log(x_pred))
    pred_mean = np.exp(intercept_mean + slope_mean * np.log(x_pred))
    
    print(f"Modelo ajustado p2p: residuo_p2p = exp({intercept_p2p:.4f}) * (Tc/tau)^{slope_p2p:.4f}")
    print(f"Modelo ajustado mean: disp_mean = exp({intercept_mean:.4f}) * (Tc/tau)^{slope_mean:.4f}")
    print(f"PREDICCION FORMAL a priori para Tc = 3.0 s (Tc/tau = {x_pred:.1f}):")
    print(f"  p2p_disp esperado = {pred_p2p:.5f} (Banda +-20%: [{pred_p2p*0.80:.5f}, {pred_p2p*1.20:.5f}])")
    print(f"  disp_mean esperada = {pred_mean:.5f} (Banda +-20%: [{pred_mean*0.80:.5f}, {pred_mean*1.20:.5f}])")
    
    # Ejecutar corrida para Tc = 3.0 s
    print("\nEjecutando corrida de verificacion para Tc = 3.0 s...")
    create_scenario("ESC-HIL-022_prediccion_Tc_30s", consensus_interval=3.0)
    run_dir_tc3 = run_scenario("ESC-HIL-022_prediccion_Tc_30s", steps=361)
    metrics_tc3 = analyze_telemetry(run_dir_tc3, tc_val=3.0)
    metrics_tc3["Tc/tau_droop"] = 3.0 / tau_droop_efectivo
    
    error_p2p = (metrics_tc3["p2p_disp"] - pred_p2p) / pred_p2p * 100.0
    error_mean = (metrics_tc3["disp_media"] - pred_mean) / pred_mean * 100.0
    print(f"\nRESULTADOS MEDIDOS Tc = 3.0 s:")
    print(f"  p2p_disp medido = {metrics_tc3['p2p_disp']:.5f} | Error frente a prediccion: {error_p2p:+.2f}%")
    print(f"  disp_mean medido = {metrics_tc3['disp_media']:.5f} | Error frente a prediccion: {error_mean:+.2f}%")
    valida_p4 = abs(error_p2p) <= 20.0 and abs(error_mean) <= 20.0
    print(f"  Dictamen T2-P4: {'EXITOSO (Dentro de +-20%)' if valida_p4 else 'REPROBADO (Fuera de +-20%)'}")
    
    # 3. T2-P5: Costo de la Ventana Amplia (Latencia ante perturbacion no sincronizada a Tc/2)
    print("\n--- T2-P5: COSTO DE LA VENTANA AMPLIA (LATENCIA ANTE SEGUNDO ESCALON A Tc/2) ---")
    # Para Tc in [0.5, 2.0, 5.0] s: segundo escalon en t = 90.0 + Tc/2
    latencia_tests = {
        "Tc_05s": {"name": "ESC-HIL-023A_latencia_Tc_05s", "Tc": 0.5, "t_step": 90.0},
        "Tc_20s": {"name": "ESC-HIL-023B_latencia_Tc_20s", "Tc": 2.0, "t_step": 91.0},
        "Tc_50s": {"name": "ESC-HIL-023C_latencia_Tc_50s", "Tc": 5.0, "t_step": 92.5},
    }
    latencia_results = {}
    for k_lat, cfg_lat in latencia_tests.items():
        q_step2_cfg = {
            "nodo": 5,
            "q_step_var": 1000.0,
            "inicio_s": cfg_lat["t_step"],
            "duracion_s": 5.0
        }
        create_scenario(cfg_lat["name"], consensus_interval=cfg_lat["Tc"], q_step2=q_step2_cfg, duracion_s=120)
        run_dir_lat = run_scenario(cfg_lat["name"], steps=241)
        
        # Medir en la telemetria cuando reacciona el consenso (delta_Q_sec / dQ != 0 despues de t_step)
        # N2 (Solar) es el mejor indicador porque no tiene slack
        uq_n2_file = os.path.join(run_dir_lat, "node_2_uq.csv")
        if not os.path.exists(uq_n2_file):
            uq_n2_file = os.path.join(WORKSPACE, "output_data", "node_2_uq.csv")
        if os.path.exists(uq_n2_file):
            uq_n2 = pd.read_csv(uq_n2_file)
            pre_dq = uq_n2[uq_n2["time_s"] < cfg_lat["t_step"]]["dQ"].iloc[-1]
            post_uq = uq_n2[uq_n2["time_s"] >= cfg_lat["t_step"]]
            first_reaction = post_uq[np.abs(post_uq["dQ"] - pre_dq) > 1e-4]
            if len(first_reaction) > 0:
                t_react = first_reaction["time_s"].iloc[0]
                latencia_s = t_react - cfg_lat["t_step"]
            else:
                t_react = np.nan
                latencia_s = np.nan
        else:
            # Medir desde telemetry_rack.csv
            tel_df = pd.read_csv(os.path.join(run_dir_lat, "telemetry_rack.csv"))
            post_tel = tel_df[tel_df["time_s"] >= cfg_lat["t_step"]]
            # En t_step reacciona el droop algebraico; cuando reacciona el consenso, Q2 se incrementa sustancialmente
            q2_base = tel_df[tel_df["time_s"] == cfg_lat["t_step"]]["Q2_kvar"].values[0]
            # Primer paso posterior donde Q2 cambia por accion secundaria
            react_rows = post_tel[post_tel["Q2_kvar"] > q2_base + 0.005]
            if len(react_rows) > 0:
                t_react = react_rows["time_s"].iloc[0]
                latencia_s = t_react - cfg_lat["t_step"]
            else:
                t_react = np.nan
                latencia_s = np.nan
            
        latencia_results[k_lat] = {
            "Tc": cfg_lat["Tc"],
            "t_step": cfg_lat["t_step"],
            "t_react": t_react,
            "latencia_s": latencia_s
        }
        print(f"  {k_lat} (Tc={cfg_lat['Tc']}s): Escalon a t={cfg_lat['t_step']:.1f}s -> Primera reaccion consenso a t={t_react:.1f}s | Latencia = {latencia_s:.2f} s")
        
    # Guardar todos los resultados procesados en JSON para redactar el informe
    out_all = {
        "tau_droop": tau_droop_dict,
        "barrido_s42": {k: {"cfg": v["cfg"], "metrics": v["metrics"]} for k, v in runs_results.items()},
        "prediccion_p4": {
            "pred_p2p": pred_p2p, "pred_mean": pred_mean,
            "medido_p2p": metrics_tc3["p2p_disp"], "medido_mean": metrics_tc3["disp_media"],
            "error_p2p_pct": error_p2p, "error_mean_pct": error_mean,
            "valida": valida_p4
        },
        "latencia_p5": latencia_results
    }
    with open(os.path.join(WORKSPACE, "outputs", "custom", "resultados_so42_so43.json"), "w", encoding="utf-8") as f:
        json.dump(out_all, f, indent=2, default=str)
    print("\n[OK] Todos los resultados consolidados en outputs/custom/resultados_so42_so43.json")
    
    # Restaurar ACTIVO.txt
    with open(ACTIVO_TXT, "w", encoding="utf-8") as f:
        f.write(CANONICAL_BASELINE)
    print(f"[OK] ACTIVO.txt restaurado a {CANONICAL_BASELINE}.")

if __name__ == "__main__":
    main()
