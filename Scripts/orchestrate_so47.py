#!/usr/bin/env python3
"""
Orquestador de Ensayos SIL para S-O-47:
P1: MPPT congelado en el punto de maxima potencia (V_ref=359 V, duty=0.1025).
P2 (solo si P1 confirma p2p < 0.005): MPPT activo con paso reducido (Delta V = 0.2 V).
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
SRC_SCENARIO = os.path.join(BASE_SCENARIOS, "ESC-HIL-026A_multirate_500ms")
PYTHON_EXE = os.path.join(WORKSPACE, ".venv", "Scripts", "python.exe")
CANONICAL_BASELINE = "ESC-HIL-008_validacion_integrada"

def create_scenario(name, mppt_frozen, mppt_step_v=1.0, mppt_interval_s=0.5, mppt_v_fixed=359.0):
    dest = os.path.join(BASE_SCENARIOS, name)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(SRC_SCENARIO, dest)
    meta_path = os.path.join(dest, "meta.json")
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    meta["id"] = name.split("_")[0]
    meta["duracion_s"] = 180
    meta["dt_s"] = 0.5
    meta["consensus_interval"] = 0.5
    meta["T_c"] = 0.5
    meta["c1"] = 0.0625
    meta["c2"] = 0.0375
    meta["freeze_consensus"] = False
    meta["mppt_frozen"] = mppt_frozen
    meta["mppt_step_v"] = mppt_step_v
    meta["mppt_interval_s"] = mppt_interval_s
    meta["mppt_v_fixed"] = mppt_v_fixed
    meta["descripcion"] = f"S-O-47 MPPT test: frozen={mppt_frozen}, step_v={mppt_step_v}, interval={mppt_interval_s}"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"[OK] Escenario creado: {name} (mppt_frozen={mppt_frozen}, step_v={mppt_step_v}V)")
    return dest

def run_scenario(name):
    with open(ACTIVO_TXT, "w", encoding="utf-8") as f:
        f.write(name)
    cmd = [
        PYTHON_EXE, "-u", "-B", "Scripts/run_rack_experiment_orchestrator.py",
        "--campaign", "custom",
        "--scenario", name,
        "--steps", "361",
        "--dt", "0.5",
        "--seed", "42",
        "--local-sil",
        "--fast"
    ]
    print(f"\n>>> Ejecutando {name} (361 pasos / 180 s)...")
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
    return candidates[0]

def compute_ripple_period_crossings(times, signal):
    """Calcula el periodo promedio por cruces ascendentes de la media."""
    centered = signal - np.mean(signal)
    crossings = []
    for i in range(len(centered) - 1):
        if centered[i] <= 0.0 and centered[i + 1] > 0.0:
            # Interpolacion lineal del instante de cruce
            frac = -centered[i] / (centered[i + 1] - centered[i])
            crossings.append(times[i] + frac * (times[i + 1] - times[i]))
    if len(crossings) >= 2:
        periods = np.diff(crossings)
        return float(np.mean(periods)), len(crossings)
    return None, len(crossings)

def analyze_run(run_dir, label):
    csv_path = os.path.join(run_dir, "telemetry_rack.csv")
    df = pd.read_csv(csv_path)
    df["q1"] = df["Q1_kvar"] / 6.0
    df["q2"] = df["Q2_kvar"] / 3.0
    df["q3"] = df["Q3_kvar"] / 1.0
    df["disp"] = df[["q1", "q2", "q3"]].max(axis=1) - df[["q1", "q2", "q3"]].min(axis=1)

    cola = df[(df["time_s"] >= 150.0) & (df["time_s"] <= 180.0)]
    p2p_disp = float(cola["disp"].max() - cola["disp"].min())
    disp_mean = float(cola["disp"].mean())
    period_s, n_crossings = compute_ripple_period_crossings(cola["time_s"].values, cola["disp"].values)
    f_p2p = float(cola["f_sys_hz"].max() - cola["f_sys_hz"].min())

    v_cols = [f"V{i}_pu" for i in range(1, 9)]
    v_min = float(cola[v_cols].min().min())
    v_max = float(cola[v_cols].max().max())
    v_in_5pct = bool((v_min >= 0.95) and (v_max <= 1.05))

    p_pv_mean_kw = float(cola["P2_kW"].mean())
    p_pv_p2p_kw = float(cola["P2_kW"].max() - cola["P2_kW"].min())

    return {
        "label": label,
        "run_dir": run_dir,
        "p2p_disp": p2p_disp,
        "disp_mean": disp_mean,
        "ripple_period_s": period_s,
        "n_up_crossings": n_crossings,
        "f_sys_p2p": f_p2p,
        "f_stable": bool(f_p2p <= 0.10),
        "v_min_pu": v_min,
        "v_max_pu": v_max,
        "v_in_5pct": v_in_5pct,
        "p_pv_mean_kw": p_pv_mean_kw,
        "p_pv_p2p_kw": p_pv_p2p_kw,
    }

def main():
    print("=" * 80)
    print(" EJECUCION S-O-47: PRUEBA DECISIVA MPPT CONGELADO")
    print("=" * 80)

    # Analizar referencia 026A de resultados_so46.json
    with open(os.path.join(WORKSPACE, "outputs", "custom", "resultados_so46.json"), "r", encoding="utf-8") as f:
        so46 = json.load(f)
    dir_026a = so46["cases"][0]["run_dir"]
    ref_026a = analyze_run(dir_026a, "026A (Base MPPT 1.0V / 0.5s)")
    print(f"\n[REF 026A] p2p={ref_026a['p2p_disp']:.5f}, disp_mean={ref_026a['disp_mean']:.5f}, "
          f"T_rizado={ref_026a['ripple_period_s']:.2f}s, P_PV={ref_026a['p_pv_mean_kw']:.4f} kW (p2p={ref_026a['p_pv_p2p_kw']:.4f} kW)")

    # P1: MPPT congelado
    name_p1 = "ESC-HIL-027A_mppt_congelado"
    create_scenario(name_p1, mppt_frozen=True, mppt_v_fixed=359.0)
    dir_p1 = run_scenario(name_p1)
    res_p1 = analyze_run(dir_p1, "P1 (MPPT Congelado V=359V)")
    res_p1["delta_p_pv_kw"] = res_p1["p_pv_mean_kw"] - ref_026a["p_pv_mean_kw"]
    print(f"\n[P1] p2p={res_p1['p2p_disp']:.5f}, disp_mean={res_p1['disp_mean']:.5f}, "
          f"T_rizado={res_p1['ripple_period_s']}, P_PV={res_p1['p_pv_mean_kw']:.4f} kW (diff={res_p1['delta_p_pv_kw']:+.4f} kW, p2p={res_p1['p_pv_p2p_kw']:.4f} kW)")

    results = {"ref_026A": ref_026a, "P1": res_p1, "P2": None, "verdict": ""}

    if res_p1["p2p_disp"] < 0.005:
        print("\n>>> P1 CONFIRMA (p2p < 0.005)! Ejecutando P2 (paso reducido Delta V = 0.2 V)...")
        name_p2 = "ESC-HIL-027B_mppt_paso_02V"
        create_scenario(name_p2, mppt_frozen=False, mppt_step_v=0.2, mppt_interval_s=0.5)
        dir_p2 = run_scenario(name_p2)
        res_p2 = analyze_run(dir_p2, "P2 (MPPT Delta V = 0.2 V)")
        res_p2["delta_p_pv_kw"] = res_p2["p_pv_mean_kw"] - ref_026a["p_pv_mean_kw"]
        results["P2"] = res_p2
        results["verdict"] = "CONFIRMADO"
        print(f"\n[P2] p2p={res_p2['p2p_disp']:.5f}, disp_mean={res_p2['disp_mean']:.5f}, "
              f"T_rizado={res_p2['ripple_period_s']}, P_PV={res_p2['p_pv_mean_kw']:.4f} kW")
    else:
        print(f"\n>>> P1 REFUTA (p2p = {res_p1['p2p_disp']:.5f} >= 0.005). P2 no se ejecuta segun S-O-47.")
        results["verdict"] = "REFUTADO"

    out_json = os.path.join(WORKSPACE, "outputs", "custom", "resultados_so47.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    with open(ACTIVO_TXT, "w", encoding="utf-8") as f:
        f.write(CANONICAL_BASELINE)
    print(f"\n[OK] Veredicto S-O-47: {results['verdict']} | Resultados en {out_json}")
    print(f"[OK] ACTIVO.txt restaurado a: {CANONICAL_BASELINE}")

if __name__ == "__main__":
    main()
