#!/usr/bin/env python3
"""
Orquestador S-O-48 Parte B: Verificación SIL de ESC-HIL-029_inversor_rl_busdc y auditoría de balance AC-DC.
"""

import os
import sys
import json
import shutil
import subprocess
import time
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Solar.SistemaSolar import SistemaSolar
from Diesel.SistemaDiesel import SistemaDiesel
from BESS.SistemaBESS import SistemaBESS

WORKSPACE = r"D:\Antigravity\Projects\Tesis_Grado"
BASE_SCENARIOS = os.path.join(WORKSPACE, "Forms", "escenarios_generados")
ACTIVO_TXT = os.path.join(BASE_SCENARIOS, "ACTIVO.txt")
SRC_SCENARIO = os.path.join(BASE_SCENARIO := BASE_SCENARIOS, "ESC-HIL-026A_multirate_500ms")
PYTHON_EXE = os.path.join(WORKSPACE, ".venv", "Scripts", "python.exe")
CANONICAL_BASELINE = "ESC-HIL-008_validacion_integrada"
SCENARIO_NAME = "ESC-HIL-029_inversor_rl_busdc"


def setup_scenario():
    dest = os.path.join(BASE_SCENARIOS, SCENARIO_NAME)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(SRC_SCENARIO, dest)
    meta_path = os.path.join(dest, "meta.json")
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    meta["id"] = "ESC-HIL-029"
    meta["duracion_s"] = 180
    meta["dt_s"] = 0.5
    meta["consensus_interval"] = 0.5
    meta["T_c"] = 0.5
    meta["c1"] = 0.0625
    meta["c2"] = 0.0375
    meta["freeze_consensus"] = False
    meta["mppt_frozen"] = False
    meta["q_interp_substeps"] = 1
    meta["inverter_model"] = "RL_dq_trapezoidal + coupled_DC_bus + Z_eq + S_max_circle"
    meta["descripcion"] = (
        "S-O-48 Parte B: verificacion integral con filtro RL en dq, bus DC acoplado, "
        "impedancias Z_eq y circulo S_max activos en las tres fuentes (Tc=0.5s, c/4)"
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
        "--steps", "361",
        "--dt", "0.5",
        "--seed", "42",
        "--local-sil",
        "--fast"
    ]
    print(f"\n>>> Ejecutando {SCENARIO_NAME} (361 pasos / 180 s con inversor RL + bus DC acoplado)...")
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


def audit_ac_dc_balance():
    """Audita balance de potencia AC-DC (1 s @ 1 ms) en las tres fuentes."""
    report = {}

    # 1. Diésel N1 (5.5 kW, 1.55 kvar)
    diesel = SistemaDiesel(P_nominal=10000.0, eta=1.0, droop_enabled=False)
    max_res_d = 0.0
    for _ in range(1000):
        ctx_d = diesel.step(dt=0.001, V_pcc=110.0, setpoints={"P_ref_w": 5500.0, "Q_ref_kvar": 1.55})
        res = abs(ctx_d["P_dc_in"] - (ctx_d["Pw"] + ctx_d["P_loss_ac"] + ctx_d["P_stored_L"] + ctx_d["P_cap_dc"]))
        if 200.01 < ctx_d["Vdc"] < 599.99:
            max_res_d = max(max_res_d, res)
    report["Diesel_N1"] = {
        "P_dc_in_W": round(float(ctx_d["P_dc_in"]), 4),
        "P_ac_out_W": round(float(ctx_d["Pw"]), 4),
        "P_loss_rl_W": round(float(ctx_d["P_loss_ac"]), 4),
        "P_stored_L_W": round(float(ctx_d["P_stored_L"]), 6),
        "P_cap_dc_W": round(float(ctx_d["P_cap_dc"]), 6),
        "V_dc_final_V": round(float(ctx_d["Vdc"]), 4),
        "max_residual_W": float(max_res_d),
        "tau_rl_ms": round(diesel.inversor.tau_rl * 1000.0, 3),
        "tau_i_ms": round(diesel.inversor.tau_i * 1000.0, 3),
        "R_eq_ohm": round(diesel.inversor.R_eq, 4),
        "X_eq_ohm": round(diesel.inversor.X_eq, 4),
        "S_max_VA": round(diesel.inversor.S_max_total, 2),
    }

    # 2. Solar N2 (POA=801.78 W/m2, T=300.88 K, 0.78 kvar)
    solar = SistemaSolar(N_inv=1)
    solar.POA = 801.78
    solar.Tam = 300.88
    max_res_s = 0.0
    for _ in range(1000):
        ctx_s = solar.step(dt=0.001, V_pcc=1.0, setpoints={"Q_ref_kvar": 0.78})
        res = abs(ctx_s["P_dc_in"] - (ctx_s["Pw"] + ctx_s["P_loss_ac"] + ctx_s["P_stored_L"] + ctx_s["P_cap_dc"]))
        if 370.01 < ctx_s["V_dc"] < 499.99:
            max_res_s = max(max_res_s, res)
    report["Solar_N2"] = {
        "P_dc_in_W": round(float(ctx_s["P_dc_in"]), 4),
        "P_ac_out_W": round(float(ctx_s["Pw"]), 4),
        "P_loss_rl_W": round(float(ctx_s["P_loss_ac"]), 4),
        "P_stored_L_W": round(float(ctx_s["P_stored_L"]), 6),
        "P_cap_dc_W": round(float(ctx_s["P_cap_dc"]), 6),
        "V_dc_final_V": round(float(ctx_s["V_dc"]), 4),
        "max_residual_W": float(max_res_s),
        "tau_rl_ms": round(solar.inversor.tau_rl * 1000.0, 3),
        "tau_i_ms": round(solar.inversor.tau_i * 1000.0, 3),
        "R_eq_ohm": round(solar.inversor.R_eq, 4),
        "X_eq_ohm": round(solar.inversor.X_eq, 4),
        "S_max_VA": round(solar.inversor.S_max_total, 2),
    }

    # 3a. BESS N3 Descarga (+2000 W, 0.26 kvar)
    bess_d = SistemaBESS(N_inv=1, SoC_inicial=0.50, droop_enabled=False, S_inv_nom=3200.0)
    max_res_bd = 0.0
    for _ in range(1000):
        ctx_bd = bess_d.step(dt=0.001, V_pcc=110.0, setpoints={"P_ref_w": 2000.0, "Q_ref_kvar": 0.26})
        res = abs(ctx_bd["P_dc_in"] - (ctx_bd["Pw"] + ctx_bd["P_loss_ac"] + ctx_bd["P_stored_L"] + ctx_bd["P_cap_dc"]))
        if 360.01 < ctx_bd["V_dc"] < 439.99:
            max_res_bd = max(max_res_bd, res)
    report["BESS_N3_descarga"] = {
        "P_dc_in_W": round(float(ctx_bd["P_dc_in"]), 4),
        "P_ac_out_W": round(float(ctx_bd["Pw"]), 4),
        "P_loss_rl_W": round(float(ctx_bd["P_loss_ac"]), 4),
        "P_stored_L_W": round(float(ctx_bd["P_stored_L"]), 6),
        "P_cap_dc_W": round(float(ctx_bd["P_cap_dc"]), 6),
        "V_dc_final_V": round(float(ctx_bd["V_dc"]), 4),
        "max_residual_W": float(max_res_bd),
        "tau_rl_ms": round(bess_d.inversor.tau_rl * 1000.0, 3),
        "tau_i_ms": round(bess_d.inversor.tau_i * 1000.0, 3),
        "R_eq_ohm": round(bess_d.inversor.R_eq, 4),
        "X_eq_ohm": round(bess_d.inversor.X_eq, 4),
        "S_max_VA": round(bess_d.inversor.S_max_total, 2),
    }

    # 3b. BESS N3 Carga (-2500 W, 0.26 kvar)
    bess_c = SistemaBESS(N_inv=1, SoC_inicial=0.50, droop_enabled=False, S_inv_nom=3200.0)
    max_res_bc = 0.0
    for _ in range(1000):
        ctx_bc = bess_c.step(dt=0.001, V_pcc=110.0, setpoints={"P_ref_w": -2500.0, "Q_ref_kvar": 0.26})
        res = abs(ctx_bc["P_dc_in"] - (ctx_bc["Pw"] + ctx_bc["P_loss_ac"] + ctx_bc["P_stored_L"] + ctx_bc["P_cap_dc"]))
        if 360.01 < ctx_bc["V_dc"] < 439.99:
            max_res_bc = max(max_res_bc, res)
    report["BESS_N3_carga"] = {
        "P_dc_in_W": round(float(ctx_bc["P_dc_in"]), 4),
        "P_ac_out_W": round(float(ctx_bc["Pw"]), 4),
        "P_loss_rl_W": round(float(ctx_bc["P_loss_ac"]), 4),
        "P_stored_L_W": round(float(ctx_bc["P_stored_L"]), 6),
        "P_cap_dc_W": round(float(ctx_bc["P_cap_dc"]), 6),
        "V_dc_final_V": round(float(ctx_bc["V_dc"]), 4),
        "max_residual_W": float(max_res_bc),
        "tau_rl_ms": round(bess_c.inversor.tau_rl * 1000.0, 3),
        "tau_i_ms": round(bess_c.inversor.tau_i * 1000.0, 3),
        "R_eq_ohm": round(bess_c.inversor.R_eq, 4),
        "X_eq_ohm": round(bess_c.inversor.X_eq, 4),
        "S_max_VA": round(bess_c.inversor.S_max_total, 2),
    }

    return report


def analyze_sil(run_dir, wall_time_s):
    df = pd.read_csv(os.path.join(run_dir, "telemetry_rack.csv"))
    df["q1"] = df["Q1_kvar"] / 6.0
    df["q2"] = df["Q2_kvar"] / 3.0
    df["q3"] = df["Q3_kvar"] / 1.0
    df["disp"] = df[["q1", "q2", "q3"]].max(axis=1) - df[["q1", "q2", "q3"]].min(axis=1)

    cola = df[(df["time_s"] >= 150.0) & (df["time_s"] <= 180.0)]
    p2p_disp = float(cola["disp"].max() - cola["disp"].min())
    disp_mean = float(cola["disp"].mean())
    f_p2p = float(cola["f_sys_hz"].max() - cola["f_sys_hz"].min())

    v_cols = [f"V{i}_pu" for i in range(1, 9)]
    v_min = float(df[v_cols].min().min())
    v_max = float(df[v_cols].max().max())
    v_in_5pct = bool((v_min >= 0.95) and (v_max <= 1.05))

    step_ms = df["step_elapsed_ms"].values
    max_step_ms = float(np.max(step_ms))
    mean_step_ms = float(np.mean(step_ms))
    overruns_500 = int(np.sum(step_ms > 500.0))

    p2_mean_kw = float(cola["P2_kW"].mean())

    return {
        "scenario": SCENARIO_NAME,
        "run_dir": run_dir,
        "wall_time_s": round(wall_time_s, 2),
        "p2p_disp": p2p_disp,
        "disp_mean": disp_mean,
        "f_sys_p2p": f_p2p,
        "f_stable": bool(f_p2p <= 0.10),
        "v_min_pu": v_min,
        "v_max_pu": v_max,
        "v_in_5pct": v_in_5pct,
        "max_step_ms": max_step_ms,
        "mean_step_ms": mean_step_ms,
        "overruns_500ms": overruns_500,
        "p_pv_mean_kw": p2_mean_kw,
    }


def main():
    print("=" * 80)
    print(" EJECUCION S-O-48 PARTE B: INVERSOR RL dq + BUS DC ACOPLADO")
    print("=" * 80)

    setup_scenario()
    run_dir, wall_s = run_simulation()
    sil_res = analyze_sil(run_dir, wall_s)
    balance_audit = audit_ac_dc_balance()

    part_a_path = os.path.join(WORKSPACE, "outputs", "custom", "resultados_so48_partA.json")
    with open(part_a_path, "r", encoding="utf-8") as f:
        part_a = json.load(f)

    consolidated = {
        "part_A": part_a,
        "part_B": {
            "sil_verification": sil_res,
            "ac_dc_balance_audit": balance_audit,
        },
        "historical_boundary": {
            "algebraic_inverter_series": "ESC-HIL-001 to ESC-HIL-028",
            "rl_dc_coupled_series": "ESC-HIL-029 onwards",
        },
    }

    out_json = os.path.join(WORKSPACE, "outputs", "custom", "resultados_so48.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(consolidated, f, indent=2)

    print("\n--- Resultados SIL ESC-HIL-029 ---")
    print(f"  disp_mean:    {sil_res['disp_mean']:.5f} | p2p(disp): {sil_res['p2p_disp']:.5f}")
    print(f"  p2p(f_sys):   {sil_res['f_sys_p2p']:.4f} Hz | V in [{sil_res['v_min_pu']:.4f}, {sil_res['v_max_pu']:.4f}] pu (±5%: {sil_res['v_in_5pct']})")
    print(f"  max_step_ms:  {sil_res['max_step_ms']:.2f} ms | overruns(>500ms): {sil_res['overruns_500ms']}")
    print(f"  P_PV media:   {sil_res['p_pv_mean_kw']:.4f} kW")

    print("\n--- Auditoria Balance AC-DC (1 s @ 1 ms) ---")
    for src, b in balance_audit.items():
        print(f"  {src:16s}: P_dc_in={b['P_dc_in_W']:8.2f} W | P_ac={b['P_ac_out_W']:8.2f} W | "
              f"P_loss_rl={b['P_loss_rl_W']:6.2f} W | V_dc={b['V_dc_final_V']:.3f} V | res_max={b['max_residual_W']:.2e} W")

    with open(ACTIVO_TXT, "w", encoding="utf-8") as f:
        f.write(CANONICAL_BASELINE)
    print(f"\n[OK] Consolidado en {out_json} | ACTIVO.txt restaurado a {CANONICAL_BASELINE}")


if __name__ == "__main__":
    main()
