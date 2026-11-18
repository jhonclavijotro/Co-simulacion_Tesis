#!/usr/bin/env python3
"""
Orquestador de Ensayos SIL y Análisis Estadístico para S-O-44:
Par Gemelo con Ganancia ÷4 y Replicación por Semillas (42, 7, 13, 21).
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
CANONICAL_BASELINE = "ESC-HIL-008_validacion_integrada"

def setup_scenarios():
    """Crea los escenarios gemelos ESC-HIL-024 (Consenso Activo) y ESC-HIL-025 (Consenso Congelado)."""
    # 1. ESC-HIL-024 (G-C: Con vecinos, ganancia /4, Tc=0.5s)
    name_gc = "ESC-HIL-024_gemelo_consenso_cdiv4"
    dest_gc = os.path.join(BASE_SCENARIOS, name_gc)
    if os.path.exists(dest_gc):
        shutil.rmtree(dest_gc)
    shutil.copytree(SRC_SCENARIO, dest_gc)
    
    meta_gc_path = os.path.join(dest_gc, "meta.json")
    with open(meta_gc_path, "r", encoding="utf-8") as f:
        meta_gc = json.load(f)
    meta_gc["id"] = "ESC-HIL-024"
    meta_gc["duracion_s"] = 180
    meta_gc["consensus_interval"] = 0.5
    meta_gc["T_c"] = 0.5
    meta_gc["c1"] = 0.0625
    meta_gc["c2"] = 0.0375
    meta_gc["freeze_consensus"] = False
    meta_gc["descripcion"] = "Par gemelo con ganancia /4 (c1=0.0625, c2=0.0375, Tc=0.5s) bajo consenso activo (con vecinos P2P)"
    with open(meta_gc_path, "w", encoding="utf-8") as f:
        json.dump(meta_gc, f, indent=2)
    print(f"[OK] Escenario G-C creado: {name_gc}")

    # 2. ESC-HIL-025 (G-A: Sin vecinos / congelado, ganancia /4, Tc=0.5s)
    name_ga = "ESC-HIL-025_gemelo_abierto_cdiv4"
    dest_ga = os.path.join(BASE_SCENARIOS, name_ga)
    if os.path.exists(dest_ga):
        shutil.rmtree(dest_ga)
    shutil.copytree(SRC_SCENARIO, dest_ga)
    
    meta_ga_path = os.path.join(dest_ga, "meta.json")
    with open(meta_ga_path, "r", encoding="utf-8") as f:
        meta_ga = json.load(f)
    meta_ga["id"] = "ESC-HIL-025"
    meta_ga["duracion_s"] = 180
    meta_ga["consensus_interval"] = 0.5
    meta_ga["T_c"] = 0.5
    meta_ga["c1"] = 0.0625
    meta_ga["c2"] = 0.0375
    meta_ga["freeze_consensus"] = True
    meta_ga["congelacion_modo"] = "sin vecinos / anillo desactivado / correccion deltaQ=0"
    meta_ga["descripcion"] = "Par gemelo con ganancia /4 (c1=0.0625, c2=0.0375, Tc=0.5s) bajo consenso congelado (sin vecinos P2P)"
    with open(meta_ga_path, "w", encoding="utf-8") as f:
        json.dump(meta_ga, f, indent=2)
    print(f"[OK] Escenario G-A creado: {name_ga}")
    
    return name_gc, name_ga

def run_single_simulation(scenario_name, seed, steps=361):
    """Ejecuta una corrida SIL individual con la semilla especificada."""
    with open(ACTIVO_TXT, "w", encoding="utf-8") as f:
        f.write(scenario_name)
        
    cmd = [
        PYTHON_EXE, "-u", "-B", "Scripts/run_rack_experiment_orchestrator.py",
        "--campaign", "custom",
        "--scenario", scenario_name,
        "--steps", str(steps),
        "--seed", str(seed),
        "--local-sil",
        "--fast"
    ]
    print(f"\n>>> Lanzando {scenario_name} | Semilla={seed} ({steps} pasos / 180 s)...")
    t0 = time.time()
    res = subprocess.run(cmd, cwd=WORKSPACE, capture_output=True, text=True)
    elap = time.time() - t0
    if res.returncode != 0:
        print(f"[ERROR] Fallo en la ejecucion de {scenario_name} (seed {seed}):")
        print(res.stderr[-600:])
        raise RuntimeError(f"Fallo al ejecutar {scenario_name} con seed {seed}")
    print(f"[OK] Corrida completada en {elap:.1f} s.")
    
    # Localizar el directorio de resultados más reciente con ese scenario y seed
    results_dir = os.path.join(WORKSPACE, "outputs", "custom", "results")
    candidates = [
        os.path.join(results_dir, d) for d in os.listdir(results_dir)
        if scenario_name in d and f"seed{seed}" in d
    ]
    candidates.sort(key=os.path.getmtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No se encontro carpeta de resultados para {scenario_name} seed {seed}")
    run_dir = candidates[0]
    return run_dir

def analyze_run(run_dir):
    """Calcula las métricas formales de la corrida sobre telemetry_rack.csv."""
    csv_path = os.path.join(run_dir, "telemetry_rack.csv")
    df = pd.read_csv(csv_path)
    
    # Ratios normalizados de potencia reactiva
    # N1: Q_max = 6 kvar, N2: Q_max = 3 kvar, N3: Q_max = 1 kvar
    df["q1"] = df["Q1_kvar"] / 6.0
    df["q2"] = df["Q2_kvar"] / 3.0
    df["q3"] = df["Q3_kvar"] / 1.0
    
    # Métrica única de dispersión formal
    df["disp"] = df[["q1", "q2", "q3"]].max(axis=1) - df[["q1", "q2", "q3"]].min(axis=1)
    
    # Ventana de evaluación de los últimos 30 s: t in [150.0, 180.0] s
    cola = df[(df["time_s"] >= 150.0) & (df["time_s"] <= 180.0)]
    
    disp_media = float(cola["disp"].mean())
    disp_max = float(cola["disp"].max())
    disp_min = float(cola["disp"].min())
    p2p_disp = float(disp_max - disp_min)
    
    # Estabilidad en frecuencia (p2p <= 0.10 Hz)
    f_cola = cola["f_sys_hz"]
    p2p_f = float(f_cola.max() - f_cola.min())
    
    # Leer manifiesto para extraer hash y commit
    manifest_path = os.path.join(run_dir, "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
        
    return {
        "run_dir": run_dir,
        "run_id": manifest.get("run_id"),
        "scenario": manifest.get("scenario"),
        "git_commit": manifest.get("git_commit"),
        "consensus_mode": manifest.get("consensus_mode"),
        "seed": manifest.get("parameters", {}).get("network_seed"),
        "disp_media_cola": disp_media,
        "disp_p2p_cola": p2p_disp,
        "disp_max_cola": disp_max,
        "disp_min_cola": disp_min,
        "f_sys_p2p_cola": p2p_f,
        "f_sys_stable": p2p_f <= 0.10,
        "trajectory_time": df["time_s"].tolist(),
        "trajectory_disp": df["disp"].tolist()
    }

def main():
    print("=" * 80)
    print(" EJECUCIÓN S-O-44: PAR GEMELO GANANCIA ÷4 Y REPLICACIÓN POR SEMILLAS")
    print("=" * 80)
    
    name_gc, name_ga = setup_scenarios()
    seeds = [42, 7, 13, 21]
    
    results = {
        "seeds": seeds,
        "runs": {},
        "pairs": {},
        "aggregate": {}
    }
    
    for s in seeds:
        print(f"\n{'='*30} SEMILLA {s} {'='*30}")
        # Corrida G-C (Consenso Activo)
        dir_gc = run_single_simulation(name_gc, seed=s, steps=361)
        res_gc = analyze_run(dir_gc)
        results["runs"][f"G-C_seed{s}"] = res_gc
        
        # Corrida G-A (Consenso Congelado / Lazo Abierto)
        dir_ga = run_single_simulation(name_ga, seed=s, steps=361)
        res_ga = analyze_run(dir_ga)
        results["runs"][f"G-A_seed{s}"] = res_ga
        
        # Factor por semilla: factor = disp_media(G-A) / disp_media(G-C)
        factor_s = res_ga["disp_media_cola"] / res_gc["disp_media_cola"]
        results["pairs"][str(s)] = {
            "seed": s,
            "disp_mean_GA": res_ga["disp_media_cola"],
            "disp_p2p_GA": res_ga["disp_p2p_cola"],
            "f_p2p_GA": res_ga["f_sys_p2p_cola"],
            "disp_mean_GC": res_gc["disp_media_cola"],
            "disp_p2p_GC": res_gc["disp_p2p_cola"],
            "f_p2p_GC": res_gc["f_sys_p2p_cola"],
            "factor_reduccion": factor_s
        }
        print(f"\n--- Resumen Semilla {s} ---")
        print(f"  G-A (Abierto):  disp={res_ga['disp_media_cola']:.5f} (p2p={res_ga['disp_p2p_cola']:.5f}, p2p_f={res_ga['f_sys_p2p_cola']:.4f} Hz)")
        print(f"  G-C (Consenso): disp={res_gc['disp_media_cola']:.5f} (p2p={res_gc['disp_p2p_cola']:.5f}, p2p_f={res_gc['f_sys_p2p_cola']:.4f} Hz)")
        print(f"  --> Factor de Reducción: {factor_s:.2f}x")

    # Estadísticas agregadas
    factors = [results["pairs"][str(s)]["factor_reduccion"] for s in seeds]
    disp_ga_list = [results["pairs"][str(s)]["disp_mean_GA"] for s in seeds]
    disp_gc_list = [results["pairs"][str(s)]["disp_mean_GC"] for s in seeds]
    p2p_gc_list = [results["pairs"][str(s)]["disp_p2p_GC"] for s in seeds]
    f_p2p_all = [
        results["pairs"][str(s)]["f_p2p_GA"] for s in seeds
    ] + [
        results["pairs"][str(s)]["f_p2p_GC"] for s in seeds
    ]
    
    results["aggregate"] = {
        "factor_mean": float(np.mean(factors)),
        "factor_std": float(np.std(factors)),
        "factor_min": float(np.min(factors)),
        "factor_max": float(np.max(factors)),
        "disp_mean_GA_mean": float(np.mean(disp_ga_list)),
        "disp_mean_GC_mean": float(np.mean(disp_gc_list)),
        "disp_p2p_GC_mean": float(np.mean(p2p_gc_list)),
        "max_f_p2p": float(np.max(f_p2p_all)),
        "all_freq_stable": bool(np.max(f_p2p_all) <= 0.10)
    }
    
    out_json = os.path.join(WORKSPACE, "outputs", "custom", "resultados_so44.json")
    with open(out_json, "w", encoding="utf-8") as f:
        # Serializar omitiendo trayectorias largas para el json resumen
        summary = {
            "seeds": results["seeds"],
            "pairs": results["pairs"],
            "aggregate": results["aggregate"],
            "manifest_details": {
                k: {
                    "run_id": v["run_id"],
                    "git_commit": v["git_commit"],
                    "consensus_mode": v["consensus_mode"],
                    "seed": v["seed"],
                    "disp_media_cola": v["disp_media_cola"],
                    "disp_p2p_cola": v["disp_p2p_cola"],
                    "f_sys_p2p_cola": v["f_sys_p2p_cola"]
                } for k, v in results["runs"].items()
            },
            # Guardamos trayectoria de seed 42 para la serie temporal superpuesta
            "trajectory_seed42": {
                "time_s": results["runs"]["G-C_seed42"]["trajectory_time"],
                "disp_GC": results["runs"]["G-C_seed42"]["trajectory_disp"],
                "disp_GA": results["runs"]["G-A_seed42"]["trajectory_disp"]
            }
        }
        json.dump(summary, f, indent=2)
        
    print("\n" + "=" * 80)
    print(" SINTESIS AGREGADA S-O-44 (4 Semillas: 42, 7, 13, 21)")
    print("=" * 80)
    print(f" - Dispersión Media Lazo Abierto (G-A):   {results['aggregate']['disp_mean_GA_mean']:.5f}")
    print(f" - Dispersión Media Consenso FxTS (G-C):   {results['aggregate']['disp_mean_GC_mean']:.5f}")
    print(f" - Rizado Residual p2p Consenso (G-C):    {results['aggregate']['disp_p2p_GC_mean']:.5f}")
    print(f" - Factor de Reducción Medio:             {results['aggregate']['factor_mean']:.2f}x (std: {results['aggregate']['factor_std']:.2f})")
    print(f" - Rango de Factor [min, max]:            [{results['aggregate']['factor_min']:.2f}x, {results['aggregate']['factor_max']:.2f}x]")
    print(f" - Maximo p2p(f_sys):                     {results['aggregate']['max_f_p2p']:.4f} Hz (Estabilidad <= 0.10 Hz: {results['aggregate']['all_freq_stable']})")
    print(f" - Resultados exportados en: {out_json}")
    
    # Restaurar escenario canonico activo
    with open(ACTIVO_TXT, "w", encoding="utf-8") as f:
        f.write(CANONICAL_BASELINE)
    print(f"[OK] ACTIVO.txt restaurado a: {CANONICAL_BASELINE}")

if __name__ == "__main__":
    main()
