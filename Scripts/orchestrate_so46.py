#!/usr/bin/env python3
"""
Orquestador de Ensayos SIL y Análisis Multi-Rate para S-O-46:
Solucionador a 500 ms, 250 ms (2:1) y 125 ms (4:1) con Consenso Fijo a 500 ms (Tc=0.5s, c1/4, c2/4).
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
SRC_SCENARIO = os.path.join(BASE_SCENARIOS, "ESC-HIL-024_gemelo_consenso_cdiv4")
PYTHON_EXE = os.path.join(WORKSPACE, ".venv", "Scripts", "python.exe")
CANONICAL_BASELINE = "ESC-HIL-008_validacion_integrada"

CASES = [
    {"name": "ESC-HIL-026A_multirate_500ms", "label": "Base (500 ms)", "dt_s": 0.5, "steps": 361, "pred_p2p": 0.0148},
    {"name": "ESC-HIL-026B_multirate_250ms", "label": "2:1 (250 ms)", "dt_s": 0.25, "steps": 721, "pred_p2p": 0.0074},
    {"name": "ESC-HIL-026C_multirate_125ms", "label": "4:1 (125 ms)", "dt_s": 0.125, "steps": 1441, "pred_p2p": 0.0037},
]

def setup_scenarios():
    for c in CASES:
        dest = os.path.join(BASE_SCENARIOS, c["name"])
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(SRC_SCENARIO, dest)
        meta_path = os.path.join(dest, "meta.json")
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        meta["id"] = c["name"].split("_")[0]
        meta["duracion_s"] = 180
        meta["dt_s"] = c["dt_s"]
        meta["consensus_interval"] = 0.5
        meta["T_c"] = 0.5
        meta["c1"] = 0.0625
        meta["c2"] = 0.0375
        meta["freeze_consensus"] = False
        meta["descripcion"] = f"S-O-46 Multi-rate {c['label']}: solver dt={c['dt_s']}s, consenso fijo Tc=0.5s (c1=0.0625, c2=0.0375)"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        print(f"[OK] Escenario creado: {c['name']} (dt_pf={c['dt_s']}s, steps={c['steps']}, Tc=0.5s)")

def run_case(case):
    name = case["name"]
    with open(ACTIVO_TXT, "w", encoding="utf-8") as f:
        f.write(name)

    cmd = [
        PYTHON_EXE, "-u", "-B", "Scripts/run_rack_experiment_orchestrator.py",
        "--campaign", "custom",
        "--scenario", name,
        "--steps", str(case["steps"]),
        "--dt", str(case["dt_s"]),
        "--seed", "42",
        "--local-sil",
        "--fast"
    ]
    print(f"\n>>> Ejecutando {name} ({case['steps']} pasos @ dt={case['dt_s']*1000:.0f} ms)...")
    t0 = time.time()
    res = subprocess.run(cmd, cwd=WORKSPACE, capture_output=True, text=True)
    elap = time.time() - t0
    if res.returncode != 0:
        print(f"[ERROR] Fallo en {name}:")
        print(res.stderr[-600:])
        raise RuntimeError(f"Fallo al ejecutar {name}")
    print(f"[OK] Completado {name} en {elap:.1f} s.")

    results_dir = os.path.join(WORKSPACE, "outputs", "custom", "results")
    candidates = [os.path.join(results_dir, d) for d in os.listdir(results_dir) if name in d]
    candidates.sort(key=os.path.getmtime, reverse=True)
    return candidates[0], elap

def analyze_case(run_dir, case, wall_time_s):
    dt_s = case["dt_s"]
    rack_csv = os.path.join(run_dir, "telemetry_rack.csv")
    full_csv = os.path.join(run_dir, "telemetry_solver_full.csv")
    if not os.path.exists(full_csv):
        full_csv = rack_csv

    df_2hz = pd.read_csv(rack_csv)
    df_full = pd.read_csv(full_csv)

    for df in (df_2hz, df_full):
        df["q1"] = df["Q1_kvar"] / 6.0
        df["q2"] = df["Q2_kvar"] / 3.0
        df["q3"] = df["Q3_kvar"] / 1.0
        df["disp"] = df[["q1", "q2", "q3"]].max(axis=1) - df[["q1", "q2", "q3"]].min(axis=1)

    # Ventana de cola [150, 180] s en telemetria canonica 2 Hz
    cola_2hz = df_2hz[(df_2hz["time_s"] >= 150.0) & (df_2hz["time_s"] <= 180.0)]
    cola_full = df_full[(df_full["time_s"] >= 150.0) & (df_full["time_s"] <= 180.0)]

    p2p_2hz = float(cola_2hz["disp"].max() - cola_2hz["disp"].min())
    mean_2hz = float(cola_2hz["disp"].mean())
    p2p_full = float(cola_full["disp"].max() - cola_full["disp"].min())
    mean_full = float(cola_full["disp"].mean())
    p2p_f = float(cola_2hz["f_sys_hz"].max() - cola_2hz["f_sys_hz"].min())

    # Correlacion P_net(k+1) vs balance(k) = P_gen(k) - P_load(k) sobre pasos del solucionador
    df_full["p_gen_tot"] = df_full["P1_kW"] + df_full["P2_kW"] + df_full["P3_kW"]
    df_full["balance_k"] = df_full["p_gen_tot"] - df_full["P_load_total_kW"]
    # En PowerFlowClockServer, P_net_kW es la potencia neta inyectada por el slack/red en el paso k+1
    # Calculamos correlacion a lag 0 y lag 1 (en pasos de solucionador)
    pnet_next = df_full["P_net_kW"].iloc[1:].values
    bal_curr = df_full["balance_k"].iloc[:-1].values
    corr_lag1 = float(np.corrcoef(pnet_next, bal_curr)[0, 1]) if len(pnet_next) > 2 else np.nan
    corr_lag0 = float(np.corrcoef(df_full["P_net_kW"].values, df_full["balance_k"].values)[0, 1])

    # Tiempos de paso y overruns
    # Excluimos step 0 si incluye margen de suscripcion o medimos todos los pasos
    step_ms = df_full["step_elapsed_ms"].values
    max_step_ms = float(np.max(step_ms))
    mean_step_ms = float(np.mean(step_ms))
    p99_step_ms = float(np.percentile(step_ms, 99))
    overruns_125 = int(np.sum(step_ms > 125.0))
    overruns_budget = int(np.sum(step_ms > (dt_s * 1000.0)))

    # Evaluacion de la prediccion (+/- 30 %)
    pred = case["pred_p2p"]
    rel_err_pct = ((p2p_2hz - pred) / pred) * 100.0
    within_30 = abs(rel_err_pct) <= 30.0

    return {
        "name": case["name"],
        "label": case["label"],
        "dt_ms": int(round(dt_s * 1000)),
        "steps_solver": len(df_full),
        "steps_telemetry_2hz": len(df_2hz),
        "run_dir": run_dir,
        "wall_time_s": round(wall_time_s, 2),
        "p2p_2hz": p2p_2hz,
        "p2p_full": p2p_full,
        "disp_mean_2hz": mean_2hz,
        "disp_mean_full": mean_full,
        "pred_p2p": pred,
        "rel_err_pct": rel_err_pct,
        "within_30pct": bool(within_30),
        "corr_lag1_pnet_bal": corr_lag1,
        "corr_lag0_pnet_bal": corr_lag0,
        "effective_delay_ms": int(round(dt_s * 1000)),
        "max_step_ms": max_step_ms,
        "mean_step_ms": mean_step_ms,
        "p99_step_ms": p99_step_ms,
        "overruns_125ms": overruns_125,
        "overruns_step_budget": overruns_budget,
        "f_sys_p2p": p2p_f,
        "f_sys_stable": bool(p2p_f <= 0.10),
    }

def main():
    print("=" * 80)
    print(" EJECUCION S-O-46: MULTI-RATE (500 / 250 / 125 ms) CON CONSENSO FIJO 500 ms")
    print("=" * 80)

    setup_scenarios()
    summary = {"cases": [], "verdict": ""}

    for c in CASES:
        run_dir, wall_s = run_case(c)
        metrics = analyze_case(run_dir, c, wall_s)
        summary["cases"].append(metrics)
        print(f"\n--- Resultados {c['label']} ---")
        print(f"  p2p(2Hz): {metrics['p2p_2hz']:.5f} (pred: {metrics['pred_p2p']:.4f}, err: {metrics['rel_err_pct']:+.1f}%, +-30%: {metrics['within_30pct']})")
        print(f"  p2p(full): {metrics['p2p_full']:.5f} | disp_media: {metrics['disp_mean_2hz']:.5f}")
        print(f"  corr lag1 (P_net[k+1], bal[k]): {metrics['corr_lag1_pnet_bal']:.4f} | lag0: {metrics['corr_lag0_pnet_bal']:.4f}")
        print(f"  max_step_ms: {metrics['max_step_ms']:.3f} ms | mean: {metrics['mean_step_ms']:.3f} ms | overruns(>125ms): {metrics['overruns_125ms']}")
        print(f"  f_sys p2p: {metrics['f_sys_p2p']:.4f} Hz (<=0.10 Hz: {metrics['f_sys_stable']})")

    # Veredicto automatico preliminar
    c_base, c_21, c_41 = summary["cases"]
    if c_21["within_30pct"] and c_41["within_30pct"] and (c_41["p2p_2hz"] < c_21["p2p_2hz"] < c_base["p2p_2hz"]):
        verdict = "CUANTIZACIÓN CONFIRMADA"
    elif (c_41["p2p_2hz"] >= 0.85 * c_base["p2p_2hz"]) and (c_21["p2p_2hz"] >= 0.85 * c_base["p2p_2hz"]):
        verdict = "CUANTIZACIÓN REFUTADA"
    else:
        verdict = "INCONCLUSA / PARCIAL"
    summary["verdict"] = verdict

    out_json = os.path.join(WORKSPACE, "outputs", "custom", "resultados_so46.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 80)
    print(f" VEREDICTO S-O-46: {verdict}")
    print(f" Resultados guardados en: {out_json}")
    print("=" * 80)

    with open(ACTIVO_TXT, "w", encoding="utf-8") as f:
        f.write(CANONICAL_BASELINE)
    print(f"[OK] ACTIVO.txt restaurado a: {CANONICAL_BASELINE}")

if __name__ == "__main__":
    main()
