"""
Módulo de Métricas y Gates de Aceptación (v2) para el Benchmark FxTS.
Tesis de Grado: Control Secundario Distribuido en Tiempo Fijo.
Referencias:
  - benchmark-spec-v2.md
  - Energies 2023, 16(1), 517 (DOI: 10.3390/en16010517) - Ecs. 11-16
  - IEEE TIE 2015, 62(11), 7046-7055 (DOI: 10.1109/TIE.2015.2436879)
  - Appl. Sci. 2024, 14(3), 997 (DOI: 10.3390/app14030997)
"""

import math
import numpy as np
from typing import Dict, Any, List, Tuple, Optional


def calculate_settling_time(
    time: np.ndarray,
    error_signal: np.ndarray,
    tolerance_abs: Optional[float] = None,
    band_pct: Optional[float] = None,
    step_size: Optional[float] = None,
    t_start: float = 0.0
) -> Optional[float]:
    """
    Calcula el tiempo de asentamiento t_s a partir del cual el error entra y
    permanece dentro de la tolerancia para todo t' >= t_s.

    Parámetros:
        time:          Vector temporal [s].
        error_signal:  Serie del error |e(t)|.
        tolerance_abs: Tolerancia absoluta directa (ej. 0.100 Hz, 0.005 pu).
        band_pct:      Tolerancia porcentual relativa al escalón (ej. 0.05 para 5%).
        step_size:     Amplitud del escalón de perturbación |Delta x_step|.
        t_start:       Instante de inicio de la perturbación [s].
    """
    if len(time) == 0 or len(error_signal) == 0:
        return None

    mask = time >= t_start
    t_sub = time[mask]
    e_sub = np.abs(error_signal[mask])

    if len(t_sub) == 0:
        return None

    if tolerance_abs is not None and tolerance_abs > 0:
        tolerance = float(tolerance_abs)
    elif band_pct is not None and band_pct > 0:
        scale = float(step_size) if (step_size is not None and step_size > 0) else float(np.max(e_sub))
        tolerance = band_pct * scale
    else:
        tolerance = 0.01

    # Verificar si hubo perturbación efectiva que superó la banda
    max_observed = float(np.max(e_sub))
    if max_observed <= tolerance:
        # La señal nunca superó la banda durante la ventana
        # Si no hubo excursión, no es un transitorio evaluable
        return 0.0

    violations = np.where(e_sub > tolerance)[0]
    if len(violations) == 0:
        return float(t_sub[0] - t_start)

    last_violation_idx = violations[-1]
    if last_violation_idx == len(t_sub) - 1:
        # Termina la simulación violando la banda: no asentó
        return None

    t_settled = float(t_sub[last_violation_idx + 1] - t_start)
    return round(t_settled, 4)


def calculate_peak_to_peak(
    signal: np.ndarray,
    time: np.ndarray,
    t_steady_start: float
) -> float:
    """Calcula el rizado pico a pico (peak-to-peak) en estado estacionario."""
    mask = time >= t_steady_start
    if not np.any(mask):
        mask = time >= (time[-1] * 0.7)
    sub = signal[mask]
    if len(sub) == 0:
        return 0.0
    return float(np.max(sub) - np.min(sub))


def calculate_overshoot(
    signal: np.ndarray,
    nominal_val: float,
    steady_val: float,
    step_change: float
) -> float:
    """Calcula el sobreimpulso porcentual relativo al escalón."""
    if abs(step_change) < 1e-6:
        return 0.0
    peak = np.max(signal) if step_change > 0 else np.min(signal)
    overshoot = abs(peak - steady_val) / abs(step_change) * 100.0
    return float(overshoot)


def calculate_rocof(
    freq_series: np.ndarray,
    time: np.ndarray,
    window_s: float = 0.5
) -> float:
    """Calcula la máxima tasa de cambio de frecuencia (RoCoF) en Hz/s."""
    if len(freq_series) < 2:
        return 0.0
    df = np.diff(freq_series)
    dt = np.diff(time)
    dt[dt <= 0] = 1e-6
    rocof_inst = np.abs(df / dt)
    return float(np.max(rocof_inst))


def calculate_rmse(signal: np.ndarray, reference: float) -> float:
    """Error cuadrático medio relativo a una referencia fija."""
    if len(signal) == 0:
        return 0.0
    return float(np.sqrt(np.mean((signal - reference) ** 2)))


def calculate_iae(error_series: np.ndarray, dt: float) -> float:
    """Integral del error absoluto (IAE): J = integral |e(t)| dt."""
    return float(np.sum(np.abs(error_series)) * dt)


def evaluate_gates(
    metrics: Dict[str, Any],
    thresholds: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """
    Evalúa los 8 Gates de Aceptación (G1 a G8) contra los umbrales configurados.

    Retorna dict con {Gate_ID: {name, passed, value, threshold, operator, unit, description}}
    """
    gates_result = {}

    divergence = bool(metrics.get("divergence", False))

    # G1: Settling time normativo (|e_f| <= 0.100 Hz) <= T_f
    t_s_norm = metrics.get("t_s_norm")
    th_g1 = thresholds.get("G1_t_s_norm_s", 52.54)
    g1_pass = (t_s_norm is not None) and (t_s_norm <= th_g1) and (not divergence)
    gates_result["G1"] = {
        "name": "Tiempo de asentamiento normativo",
        "passed": bool(g1_pass),
        "value": t_s_norm if (t_s_norm is not None and not divergence) else float("inf"),
        "threshold": th_g1,
        "operator": "<=",
        "unit": "s",
        "description": "t_s a banda normativa (|e_f| <= 0.10 Hz) <= cota Lyapunov T_f"
    }

    # G2: Delta f peak-to-peak < 0.200 Hz
    # Condición rigurosa (resuelve A5): Solo aprueba si el sistema restauró y no divergió
    df_pp = metrics.get("delta_f_pp", 0.0)
    th_g2 = thresholds.get("G2_delta_f_pp", 0.200)
    restored = metrics.get("max_e_omega_hz", 0.0) <= thresholds.get("G6_max_e_omega_hz", 0.100)
    g2_pass = (df_pp < th_g2) and (not divergence) and restored
    gates_result["G2"] = {
        "name": "Oscilacion de frecuencia pico a pico",
        "passed": bool(g2_pass),
        "value": round(df_pp, 4) if not divergence else 99.9,
        "threshold": th_g2,
        "operator": "<",
        "unit": "Hz",
        "description": "Amplitud ciclo limite en estado estacionario restaurado"
    }

    # G3: Error de reparto de reactiva max|eta_Qi - eta_Qj| < 0.020
    diff_q = metrics.get("max_diff_eta_Q", 0.0)
    th_g3 = thresholds.get("G3_max_diff_eta_Q", 0.020)
    g3_pass = (diff_q < th_g3) and (not divergence)
    gates_result["G3"] = {
        "name": "Error de reparto de potencia reactiva",
        "passed": bool(g3_pass),
        "value": round(diff_q, 4),
        "threshold": th_g3,
        "operator": "<",
        "unit": "p.u.",
        "description": "Desviacion max entre ratios Q_i / Q_max"
    }

    # G4: Error de reparto de activa max|eta_Pi - eta_Pj| < 0.020
    diff_p = metrics.get("max_diff_eta_P", 0.0)
    th_g4 = thresholds.get("G4_max_diff_eta_P", 0.020)
    g4_pass = (diff_p < th_g4) and (not divergence)
    gates_result["G4"] = {
        "name": "Error de reparto de potencia activa",
        "passed": bool(g4_pass),
        "value": round(diff_p, 4),
        "threshold": th_g4,
        "operator": "<",
        "unit": "p.u.",
        "description": "Desviacion max entre ratios P_i / P_max"
    }

    # G5: Error de restauracion de tension |e_V| <= 0.005 pu (+-0.5%)
    e_v = metrics.get("max_e_V_pu", 0.0)
    th_g5 = thresholds.get("G5_max_e_V_pu", 0.005)
    g5_pass = (e_v <= th_g5) and (not divergence)
    gates_result["G5"] = {
        "name": "Error de restauracion de tension",
        "passed": bool(g5_pass),
        "value": round(e_v, 4) if not divergence else float("inf"),
        "threshold": th_g5,
        "operator": "<=",
        "unit": "p.u.",
        "description": "Banda objetivo secundario +-0.5% (Energies eq. 12)"
    }

    # G6: Error de restauracion de frecuencia |e_omega| <= 0.100 Hz
    e_w = metrics.get("max_e_omega_hz", 0.0)
    th_g6 = thresholds.get("G6_max_e_omega_hz", 0.100)
    g6_pass = (e_w <= th_g6) and (not divergence)
    gates_result["G6"] = {
        "name": "Error de restauracion de frecuencia",
        "passed": bool(g6_pass),
        "value": round(e_w, 4) if not divergence else float("inf"),
        "threshold": th_g6,
        "operator": "<=",
        "unit": "Hz",
        "description": "Banda objetivo secundario +-0.1 Hz (Energies eq. 11)"
    }

    # G7: Estabilidad CFL discreta calculada analiticamente (resuelve A4)
    cfl_num = metrics.get("cfl_number", 0.0)
    cfl_ok = bool(metrics.get("cfl_stable", False)) and (cfl_num < 1.0) and (not divergence)
    gates_result["G7"] = {
        "name": "Estabilidad CFL discreta",
        "passed": bool(cfl_ok),
        "value": round(cfl_num, 4),
        "threshold": 1.0,
        "operator": "<",
        "unit": "num",
        "description": "Numero CFL: dt * d_max * (c1 + c2) < 1.0"
    }

    # G8: Retardo de comunicacion critico tau_crit >= 100 ms (resuelve A4)
    tau_crit = metrics.get("tau_crit_ms", 0.0)
    th_g8 = thresholds.get("G8_tau_crit_ms", 100.0)
    g8_pass = (tau_crit >= th_g8) and (not divergence)
    gates_result["G8"] = {
        "name": "Tolerancia a retardo de red (tau_crit)",
        "passed": bool(g8_pass),
        "value": round(tau_crit, 1),
        "threshold": th_g8,
        "operator": ">=",
        "unit": "ms",
        "description": "Margen de retardo admisible medido empíricamente"
    }

    return gates_result
