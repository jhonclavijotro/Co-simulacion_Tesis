#!/usr/bin/env python3
"""
Orquestador S-O-48 Parte A: Corrida discriminante ESC-HIL-028_setpoint_subpaso.
Ejecutar ANTES de ampliar GridConnectedInverter para comparabilidad estricta con 026A.
"""

import os
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
SCENARIO_NAME = "ESC-HIL-028_setpoint_subpaso"


def setup_scenario():
    dest = os.path.join(BASE_SCENARIOS, SCENARIO_NAME)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(SRC_SCENARIO, dest)
    meta_path = os.path.join(dest, "meta.json")
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    meta["id"] = "ESC-HIL-028"
    meta["duracion_s"] = 180
    meta["dt_s"] = 0.125
    meta["consensus_interval"] = 0.5
    meta["T_c"] = 0.5
    meta["c1"] = 0.0625
    meta["c2"] = 0.0375
    meta["q_interp_substeps"] = 4
    meta["freeze_consensus"] = False
    meta["descripcion"] = (
        "S-O-48 Parte A: consigna Q_ref interpolada en 4 sub-pasos de 125 ms "
        "con consenso fijo a 500 ms (c1=0.0625, c2=0.0375)"
    )
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"[OK] Escenario creado: {SCENARIO_NAME}")


def run_simulation():
    with open(ACTIVO_TXT, "w", encoding="utf-8") as f:
        f.write(SCENARIO_NAME)

    cmd = [
        PYTHON_EXE, "-u", "-B", "Scripts/run_rack_experiment_orchestrator.py",
        "--campaign", "custom",
        "--scenario", SCENARIO_NAME,
        "--steps", "1441",
        "--dt", "0.125",
        "--seed", "42",
        "--local-sil",
        "--fast"
    ]
    print(f"\n>>> Ejecutando {SCENARIO_NAME} (1441 pasos @ dt=125 ms, consenso fijo 500 ms, interp=4)...")
    t0 = time.time()
    res = subprocess.run(cmd, cwd=WORKSPACE, capture_output=True, text=True)
    elap = time.time() - t0
    if res.returncode != 0:
        print(f"[ERROR] Fallo en {SCENARIO_NAME}:")
        print(res.stderr[-600:])
        raise RuntimeError(f"Fallo al ejecutar {SCENARIO_NAME}")
    print(f"[OK] Completado {SCENARIO_NAME} en {elap:.1f} s.")

    results_dir = os.path.join(WORKSPACE, "outputs", "custom", "results")
    candidates = [os.path.join(results_dir, d) for d in os.listdir(results_dir) if SCENARIO_NAME in d]
    candidates.sort(key=os.path.getmtime, reverse=True)
    return candidates[0], elap


def analyze(run_dir, wall_time_s):
    rack_csv = os.path.join(run_dir, "telemetry_rack.csv")
    full_csv = os.path.join(run_dir, "telemetry_solver_full.csv")
    df_2hz = pd.read_csv(rack_csv)
    df_full = pd.read_csv(full_csv)

    for df in (df_2hz, df_full):
        df["q1"] = df["Q1_kvar"] / 6.0
        df["q2"] = df["Q2_kvar"] / 3.0
        df["q3"] = df["Q3_kvar"] / 1.0
        df["disp"] = df[["q1", "q2", "q3"]].max(axis=1) - df[["q1", "q2", "q3"]].min(axis=1)
        df["Q_tot"] = df["Q1_kvar"] + df["Q2_kvar"] + df["Q3_kvar"]

    cola_2hz = df_2hz[(df_2hz["time_s"] >= 150.0) & (df_2hz["time_s"] <= 180.0)]
    cola_full = df_full[(df_full["time_s"] >= 150.0) & (df_full["time_s"] <= 180.0)]

    p2p_2hz = float(cola_2hz["disp"].max() - cola_2hz["disp"].min())
    mean_2hz = float(cola_2hz["disp"].mean())
    p2p_full = float(cola_full["disp"].max() - cola_full["disp"].min())
    mean_full = float(cola_full["disp"].mean())
    f_p2p = float(cola_2hz["f_sys_hz"].max() - cola_2hz["f_sys_hz"].min())

    v_cols = [f"V{i}_pu" for i in range(1, 9)]
    v_min = float(df_2hz[v_cols].min().min())
    v_max = float(df_2hz[v_cols].max().max())

    step_ms = df_full["step_elapsed_ms"].values
    max_step_ms = float(np.max(step_ms))
    overruns_125 = int(np.sum(step_ms > 125.0))

    # Descomposicion fisica del rizado por nodo
    decomp = {
        "p2p_q1": float(cola_2hz["q1"].max() - cola_2hz["q1"].min()),
        "p2p_q2": float(cola_2hz["q2"].max() - cola_2hz["q2"].min()),
        "p2p_q3": float(cola_2hz["q3"].max() - cola_2hz["q3"].min()),
        "p2p_Qtot_over_6": float((cola_2hz["Q_tot"].max() - cola_2hz["Q_tot"].min()) / 6.0),
    }

    # Trayectoria muestreada en hitos [0, 180] s y muestra fina en [150, 160] s
    hitos = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 52.5, 55.0, 60.0, 70.0, 80.0, 100.0, 120.0, 140.0, 150.0, 151.0, 151.5, 152.0, 153.0, 160.0, 170.0, 180.0]
    traj = []
    for t_target in hitos:
        idx = int((df_2hz["time_s"] - t_target).abs().idxmin())
        row = df_2hz.loc[idx]
        traj.append({
            "time_s": float(row["time_s"]),
            "disp": float(row["disp"]),
            "q1": float(row["q1"]),
            "q2": float(row["q2"]),
            "q3": float(row["q3"]),
            "Q_tot_kvar": float(row["Q_tot"]),
        })

    if p2p_2hz < 0.006:
        verdict = "CONFIRMADO"
    elif p2p_2hz >= 0.010:
        verdict = "REFUTADO"
    else:
        verdict = "PARCIAL"

    out = {
        "scenario": SCENARIO_NAME,
        "run_dir": run_dir,
        "wall_time_s": round(wall_time_s, 2),
        "p2p_2hz": p2p_2hz,
        "p2p_full": p2p_full,
        "disp_mean_2hz": mean_2hz,
        "disp_mean_full": mean_full,
        "f_sys_p2p": f_p2p,
        "f_stable": bool(f_p2p <= 0.10),
        "v_min_pu": v_min,
        "v_max_pu": v_max,
        "max_step_ms": max_step_ms,
        "overruns_125ms": overruns_125,
        "decomposition": decomp,
        "trajectory_milestones": traj,
        "verdict": verdict,
    }

    out_path = os.path.join(WORKSPACE, "outputs", "custom", "resultados_so48_partA.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print("\n" + "=" * 75)
    print(f" RESULTADO S-O-48 PARTE A ({SCENARIO_NAME})")
    print("=" * 75)
    print(f"  p2p(disp) 2 Hz:   {p2p_2hz:.5f} (full: {p2p_full:.5f})")
    print(f"  disp_mean 2 Hz:   {mean_2hz:.5f}")
    print(f"  p2p(f_sys):       {f_p2p:.4f} Hz | V in [{v_min:.4f}, {v_max:.4f}] pu")
    print(f"  max_step_ms:      {max_step_ms:.2f} ms | overruns(>125ms): {overruns_125}")
    print(f"  Descomposicion:   p2p(q1)={decomp['p2p_q1']:.5f}, p2p(q2)={decomp['p2p_q2']:.5f}, p2p(q3)={decomp['p2p_q3']:.5f}, p2p(Qtot)/6={decomp['p2p_Qtot_over_6']:.5f}")
    print(f"  Veredicto Parte A: {verdict}")
    return out


def main():
    setup_scenario()
    run_dir, wall_s = run_simulation()
    analyze(run_dir, wall_s)
    with open(ACTIVO_TXT, "w", encoding="utf-8") as f:
        f.write(CANONICAL_BASELINE)
    print(f"[OK] ACTIVO.txt restaurado a: {CANONICAL_BASELINE}")


if __name__ == "__main__":
    main()
