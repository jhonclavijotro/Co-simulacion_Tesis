"""
Harness de Simulación (v2) para el Benchmark de Control Secundario.
Tesis de Grado: Control Secundario Distribuido en Tiempo Fijo (FxTS).

REGLA FUNDAMENTAL:
  El harness importa directamente el controlador bajo prueba desde
  Agents.fixed_time_consensus. No duplica ni reimplementa la lógica de control.

Actualizaciones post-auditoría S-18:
  - D-12: Bandas normativas obligatorias (+-0.10 Hz y +-0.005 pu).
  - D-13: Modelo algebraico cinemático de referencia (T1).
  - D-14: Condiciones dispersas (capacidades DER asimétricas) para activación real de G3 y G4.
  - S4: Cálculo analítico explícito de CFL (G7) y retardo admisible tau_crit (G8).
  - S5: Gate G2 reprueba si hay divergencia física o ausencia de restauración secundaria.
"""

import sys
import os
import math
import random
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from outputs.benchmark.src.baselines_v2 import get_baseline_controller, BaseSecondaryController
from outputs.benchmark.src.metrics_v2 import (
    calculate_settling_time,
    calculate_peak_to_peak,
    calculate_overshoot,
    calculate_rocof,
    calculate_rmse,
    calculate_iae,
    evaluate_gates
)


class MicrogridBenchmarkHarness:
    """
    Entorno de simulación física y ciberfísica del banco de 8 nodos con 3 DERs.
    Topología eléctrica: Red radial BT de 8 barras, 400 V.
    Topología de comunicación: Línea 1 <-> 2 <-> 3 (lambda_2 = 1.0, d_max = 2).
    """

    def __init__(self, config: Dict[str, Any]):
        self.cfg = config
        self.dt = float(config.get("network", {}).get("dt", 0.5))
        self.f_nom = float(config.get("network", {}).get("f_nom_hz", 60.0))
        self.omega_nom = 2.0 * math.pi * self.f_nom
        self.v_nom_pu = 1.0

        # Parámetros de los DERs con capacidades asimétricas/dispersas (D-14)
        self.n_agents = 3
        self.der_configs = config.get("agents", {})
        self.P_max = [float(self.der_configs.get(i, {}).get("P_max", 50000.0)) for i in range(1, 4)]
        self.Q_max = [float(self.der_configs.get(i, {}).get("Q_max", 50000.0)) for i in range(1, 4)]
        self.k_p = [float(self.der_configs.get(i, {}).get("k_p", 1e-4)) for i in range(1, 4)]
        self.k_q = [float(self.der_configs.get(i, {}).get("k_q", 1e-4)) for i in range(1, 4)]

        # Grafo de comunicación canónico (Línea 1-2-3, lambda_2 = 1.0, d_max = 2.0)
        self.d_max = float(config.get("consensus_graph", {}).get("d_max", 2.0))
        self.adj_matrix = {
            1: {2: 1.0},
            2: {1: 1.0, 3: 1.0},
            3: {2: 1.0}
        }

    def run_simulation(
        self,
        controller_name: str = "fxts",
        tuning_mode: str = "published",
        scenario_id: str = "E1",
        scenario_params: Optional[Dict[str, Any]] = None,
        negative_control_mode: Optional[str] = None,
        seed: int = 42,
        t_sim: Optional[float] = None
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Ejecuta una corrida de simulación completa con medición física y cibernética.
        """
        random.seed(seed)
        np.random.seed(seed)

        params = scenario_params or {}
        duration = t_sim or self.cfg.get("reporting", {}).get("default_t_sim", 120.0)
        t_event = params.get("t_event", self.cfg.get("reporting", {}).get("default_t_event", 20.0))
        n_steps = int(duration / self.dt) + 1
        time_arr = np.linspace(0.0, duration, n_steps)

        # 1. Instanciar controladores
        controllers: Dict[int, BaseSecondaryController] = {}
        for agent_id in range(1, 4):
            ctrl = get_baseline_controller(
                controller_name,
                agent_id=agent_id,
                tuning_mode=tuning_mode,
                P_max=self.P_max[agent_id - 1],
                Q_max=self.Q_max[agent_id - 1],
                f_ref=self.f_nom
            )
            ctrl.set_adjacency(self.adj_matrix[agent_id])
            controllers[agent_id] = ctrl

        # Aplicación de Controles Negativos (Fase D)
        if negative_control_mode == "N2":
            # Ganancias ajenas c1=0.15, c2=0.85 que violan CFL analítico: 0.5 * 2.0 * 1.0 = 1.0 >= 1.0
            for agent_id in range(1, 4):
                controllers[agent_id] = get_baseline_controller(
                    "fxts", agent_id=agent_id, c1=0.15, c2=0.85, alpha=0.5, beta=2.0
                )
                controllers[agent_id].set_adjacency(self.adj_matrix[agent_id])

        # Determinar número CFL analítico del controlador desde la instancia real (S3)
        cfl_number = self._compute_cfl_number(controllers[1], controller_name, negative_control_mode)

        # 2. Condiciones Físicas Iniciales
        P_load_nominal = params.get("P_load_init", 28000.0)
        Q_load_nominal = params.get("Q_load_init", 12000.0)

        # Reparto primario droop: reparte en partes iguales en Watts (generando unbalance de ratios eta_P, eta_Q)
        # Esto implementa D-14 (condiciones dispersas para activación real de G3 y G4)
        P = np.array([P_load_nominal / 3.0, P_load_nominal / 3.0, P_load_nominal / 3.0])
        Q = np.array([Q_load_nominal / 3.0, Q_load_nominal / 3.0, Q_load_nominal / 3.0])
        f_sys = np.array([self.f_nom, self.f_nom, self.f_nom])
        V_bus = np.array([1.0, 1.0, 1.0])

        # Despacho nominal base
        p_dispatch_nominal = P_load_nominal / 3.0
        q_dispatch_nominal = Q_load_nominal / 3.0

        # Acumuladores de corrección secundaria
        delta_V_sec = np.zeros(3)
        delta_Q_sec = np.zeros(3)
        delta_w_sec = np.zeros(3)
        delta_P_sec = np.zeros(3)

        telemetry_records = []
        messages_sent_count = 0
        bytes_transferred_count = 0

        comm_channel_buffer = []
        agent_neighbor_buffers: Dict[int, Dict[int, Dict[str, float]]] = {1: {}, 2: {}, 3: {}}

        cfl_violation_occurred = False
        divergence_detected = False

        for k, t in enumerate(time_arr):
            # A. Perturbaciones según escenario
            P_load = P_load_nominal
            Q_load = Q_load_nominal

            if scenario_id == "E1" and t >= t_event:
                step_mult = params.get("step_multiplier", 1.5)
                P_load = P_load_nominal * step_mult
                Q_load = Q_load_nominal * step_mult

            elif scenario_id == "E2" and t >= t_event:
                ramp_t = min(1.0, (t - t_event) / 15.0)
                P_load += 8000.0 * ramp_t

            elif scenario_id == "E5" and (t_event <= t <= t_event + 30.0):
                active_agents = [1, 2]
            else:
                active_agents = [1, 2, 3]

            # B. Dinámica Primaria Droop y Balance de Potencia (D-13 & D-14)
            # Conservación estricta de balance: sum(P_i) = P_load y sum(Q_i) = Q_load
            # La corrección secundaria delta_P_sec reasigna potencia entre generadores (sum delta_P_sec = 0)
            p_droop_base = P_load / len(active_agents)
            q_droop_base = Q_load / len(active_agents)

            # Normalizar delta_P_sec y delta_Q_sec para asegurar suma cero (sin creación espuria de potencia)
            active_indices = [a - 1 for a in active_agents]
            mean_dP = float(np.mean([delta_P_sec[i] for i in active_indices]))
            mean_dQ = float(np.mean([delta_Q_sec[i] for i in active_indices]))

            for idx, a_id in enumerate([1, 2, 3]):
                if a_id not in active_agents:
                    P[idx] = 0.0
                    Q[idx] = 0.0
                    continue

                # Reparto con acción de consenso secundario de activa y reactiva
                P[idx] = p_droop_base + (delta_P_sec[idx] - mean_dP)
                Q[idx] = q_droop_base + (delta_Q_sec[idx] - mean_dQ)

                # Desviación respecto al punto nominal de operación
                p_dev = P[idx] - p_dispatch_nominal
                q_dev = Q[idx] - q_dispatch_nominal

                # Dinámica droop primaria
                f_droop = self.f_nom - self.k_p[idx] * p_dev
                v_droop = self.v_nom_pu - self.k_q[idx] * q_dev

                # Restauración secundaria acumulada
                f_sys[idx] = f_droop + (delta_w_sec[idx] / (2.0 * math.pi))
                V_bus[idx] = v_droop + delta_V_sec[idx]

            # Acoplamiento eléctrico rígido en microrred BT (frecuencia sistémica unificada)
            avg_f = np.mean([f_sys[i] for i in active_indices])
            for idx in active_indices:
                f_sys[idx] = 0.85 * avg_f + 0.15 * f_sys[idx]

            # C. Capa de Comunicación Ciberfísica
            current_adj = dict(self.adj_matrix)
            if scenario_id == "E6" and t >= t_event:
                current_adj = {1: {3: 1.0}, 2: {3: 1.0}, 3: {1: 1.0, 2: 1.0}}

            packet_loss_p = params.get("packet_loss_prob", 0.10 if scenario_id == "E4" else 0.0)
            comm_delay_s = params.get("delay_s", 0.05 if scenario_id == "E3" else 0.0)

            # Envío de paquetes
            for sender_id in active_agents:
                sender_state = {
                    "V": float(V_bus[sender_id - 1]),
                    "Q_ratio": float(Q[sender_id - 1] / self.Q_max[sender_id - 1]),
                    "omega": float(f_sys[sender_id - 1] * 2.0 * math.pi),
                    "P_ratio": float(P[sender_id - 1] / self.P_max[sender_id - 1])
                }
                for neighbor_id in current_adj.get(sender_id, {}).keys():
                    if neighbor_id not in active_agents:
                        continue
                    if random.random() < packet_loss_p:
                        continue  # Paquete perdido

                    delivery_time = t + comm_delay_s
                    comm_channel_buffer.append((delivery_time, sender_id, neighbor_id, sender_state))
                    messages_sent_count += 1
                    bytes_transferred_count += 64

            # Recepción de paquetes
            remaining_buffer = []
            for item in comm_channel_buffer:
                deliv_t, from_id, to_id, payload = item
                if t >= deliv_t:
                    agent_neighbor_buffers[to_id][from_id] = payload
                else:
                    remaining_buffer.append(item)
            comm_channel_buffer = remaining_buffer

            # D. Ejecución de Control Secundario (a partir de t >= t_event)
            if t >= t_event:
                for a_id in active_agents:
                    ctrl = controllers[a_id]
                    ctrl.set_adjacency(current_adj.get(a_id, {}))

                    try:
                        dV, dQ, dw, dP = ctrl.step(
                            V_i=float(V_bus[a_id - 1]),
                            Q_i=float(Q[a_id - 1]),
                            omega_i=float(f_sys[a_id - 1] * 2.0 * math.pi),
                            P_i=float(P[a_id - 1]),
                            neighbor_states=agent_neighbor_buffers[a_id],
                            dt=self.dt
                        )
                    except ValueError:
                        cfl_violation_occurred = True
                        dV, dQ, dw, dP = 0.0, 0.0, 0.0, 0.0

                    # Inyecciones de Controles Negativos
                    if negative_control_mode == "N1":
                        # Consenso anulado u = 0 (bug de v1)
                        dV, dQ, dw, dP = 0.0, 0.0, 0.0, 0.0

                    elif negative_control_mode == "N3":
                        # Signo invertido (divergencia forzada)
                        dV = -dV * 3.0
                        dQ = -dQ * 3.0
                        dw = -dw * 3.0
                        dP = -dP * 3.0

                    delta_V_sec[a_id - 1] += dV
                    delta_Q_sec[a_id - 1] += dQ
                    delta_w_sec[a_id - 1] += dw
                    delta_P_sec[a_id - 1] += dP

                    # Saturación física anti-windup
                    delta_V_sec[a_id - 1] = max(-0.50, min(0.50, delta_V_sec[a_id - 1]))
                    delta_w_sec[a_id - 1] = max(-6.2832, min(6.2832, delta_w_sec[a_id - 1]))

            # Detección de divergencia física
            if np.any(np.abs(f_sys - self.f_nom) > 5.0) or np.any(np.abs(V_bus - 1.0) > 0.3):
                divergence_detected = True

            # Registrar telemetría
            eta_P = [P[i] / self.P_max[i] for i in range(3)]
            eta_Q = [Q[i] / self.Q_max[i] for i in range(3)]

            telemetry_records.append({
                "time": round(t, 4),
                "f_mean": float(np.mean(f_sys)),
                "f_1": float(f_sys[0]),
                "f_2": float(f_sys[1]),
                "f_3": float(f_sys[2]),
                "V_mean": float(np.mean(V_bus)),
                "V_1": float(V_bus[0]),
                "V_2": float(V_bus[1]),
                "V_3": float(V_bus[2]),
                "P_1": float(P[0]),
                "P_2": float(P[1]),
                "P_3": float(P[2]),
                "Q_1": float(Q[0]),
                "Q_2": float(Q[1]),
                "Q_3": float(Q[2]),
                "eta_P_diff": float(max(eta_P) - min(eta_P)),
                "eta_Q_diff": float(max(eta_Q) - min(eta_Q)),
                "error_f": float(abs(np.mean(f_sys) - self.f_nom)),
                "error_V": float(abs(np.mean(V_bus) - self.v_nom_pu)),
                "messages_sent": messages_sent_count,
                "bytes_transferred": bytes_transferred_count
            })

        df_telemetry = pd.DataFrame(telemetry_records)

        # 5. Cálculo de Métricas y Gates (S1, S2, S3, S4, D-18)
        metrics = self._compute_run_metrics(
            df_telemetry,
            t_event=t_event,
            duration=duration,
            cfl_number=cfl_number,
            cfl_violation=cfl_violation_occurred,
            divergence=divergence_detected,
            ctrl=controllers[1],
            ctrl_name=controller_name,
            neg_mode=negative_control_mode
        )

        return df_telemetry, metrics

    def _compute_cfl_number(self, ctrl: BaseSecondaryController, ctrl_name: str, neg_mode: Optional[str]) -> float:
        """
        Calcula el número CFL espectral analítico normalizado (S-25 A-2):
            cfl_number = 0.5 * dt * lambda_max_H * g_ef
        equivalente a la condición de Euler explícito gobernante:
            dt * lambda_max_H * g_ef < 2.0 (TEORIA.tex:218)
        donde cfl_number < 1.0 garantiza estabilidad con margen (1 - cfl_number).
        Para FxTS canónico: dt=0.5, lambda_max=3.247, g_ef=1.033 s^-1 -> cfl_number = 0.8385 (margen 16.2%).
        """
        dt = self.dt
        lambda_max_H = float(self.cfg.get("consensus_graph", {}).get("lambda_max_H", 3.247))

        if neg_mode == "N2":
            # Ganancias ajenas con violación CFL: c1=0.15, c2=0.85, alpha=0.5, beta=2.0, eps=0.001
            # g_ef = 0.15 * (1e-3)**(-0.5) + 0.85 * (1e-3)**(1.0) = 4.744 s^-1
            # cfl_number = 0.5 * 0.5 * 3.247 * 4.744 = 3.851 >= 1.0 (VIOLACIÓN SEVERA)
            g_ef = 0.15 * (0.001 ** -0.5) + 0.85 * (0.001 ** 1.0)
            return round(0.5 * dt * lambda_max_H * g_ef, 4)

        name = ctrl_name.lower()
        if "fxts" in name:
            agent = getattr(ctrl, "agent", ctrl)
            c1 = float(getattr(agent, "c1", 0.25))
            c2 = float(getattr(agent, "c2", 0.15))
            alpha = float(getattr(agent, "alpha", 0.8))
            beta = float(getattr(agent, "beta", 1.2))
            eps = float(getattr(agent, "epsilon", 0.001))
            g_ef = c1 * (eps ** (alpha - 1.0)) + c2 * (eps ** (beta - 1.0))
            return round(0.5 * dt * lambda_max_H * g_ef, 4)
        elif "fts" in name:
            c1 = float(getattr(ctrl, "c1", 0.25))
            alpha = float(getattr(ctrl, "alpha", 0.8))
            eps = float(getattr(ctrl, "epsilon", 0.001))
            g_ef = c1 * (eps ** (alpha - 1.0))
            return round(0.5 * dt * lambda_max_H * g_ef, 4)
        elif "dapi" in name:
            k = float(max(getattr(ctrl, "k_w", 0.2), getattr(ctrl, "k_v", 0.2), getattr(ctrl, "k_p", 0.2), getattr(ctrl, "k_q", 0.2)))
            g_ef = k
            return round(0.5 * dt * lambda_max_H * g_ef, 4)
        elif "droop" in name:
            return 0.0
        elif "pi" in name:
            return 0.25
        return 0.8385

    def _compute_tau_crit(
        self,
        ctrl: BaseSecondaryController,
        ctrl_name: str,
        neg_mode: Optional[str],
        divergence: bool
    ) -> Tuple[Optional[float], str]:
        """
        Calcula la cota analítica de retardo admisible tau_crit conforme a D-18 (Opción C).
        tau_crit = (2.0 / (lambda_max_H * g_ef)) - dt
        con lambda_max_H = 3.247.
        """
        if divergence or neg_mode in ["N1", "N2", "N3"]:
            return None, "N/A: Control sin lazo de consenso distribuido estable / divergente (S-23/A4)"

        name = ctrl_name.lower()
        if "droop" in name:
            return None, "N/A (Control primario local autónomo sin capa de consenso)"

        lambda_max_H = float(self.cfg.get("consensus_graph", {}).get("lambda_max_H", 3.247))
        dt = self.dt

        if "fxts" in name:
            agent = getattr(ctrl, "agent", ctrl)
            c1 = float(getattr(agent, "c1", 0.25))
            c2 = float(getattr(agent, "c2", 0.15))
            alpha = float(getattr(agent, "alpha", 0.8))
            beta = float(getattr(agent, "beta", 1.2))
            eps = float(getattr(agent, "epsilon", 0.001))
            g_ef = c1 * (eps ** (alpha - 1.0)) + c2 * (eps ** (beta - 1.0))
            tau_crit_s = (2.0 / (lambda_max_H * g_ef)) - dt
            return round(tau_crit_s * 1000.0, 1), f"g_ef={g_ef:.4f} s^-1, lambda_max={lambda_max_H}"
        elif "fts" in name:
            c1 = float(getattr(ctrl, "c1", 0.25))
            alpha = float(getattr(ctrl, "alpha", 0.8))
            eps = float(getattr(ctrl, "epsilon", 0.001))
            g_ef = c1 * (eps ** (alpha - 1.0))
            tau_crit_s = (2.0 / (lambda_max_H * g_ef)) - dt
            return round(tau_crit_s * 1000.0, 1), f"g_ef={g_ef:.4f} s^-1, lambda_max={lambda_max_H}"
        elif "dapi" in name:
            k = float(max(getattr(ctrl, "k_w", 0.2), getattr(ctrl, "k_v", 0.2), getattr(ctrl, "k_p", 0.2), getattr(ctrl, "k_q", 0.2)))
            g_ef = k
            tau_crit_s = (2.0 / (lambda_max_H * g_ef)) - dt
            return round(tau_crit_s * 1000.0, 1), f"g_ef={g_ef:.4f} s^-1, lambda_max={lambda_max_H}"
        elif "pi" in name:
            return None, "N/A (Control secundario centralizado PI sin capa de consenso distribuido)"

        return None, "N/A"

    def _compute_run_metrics(
        self,
        df: pd.DataFrame,
        t_event: float,
        duration: float,
        cfl_number: float,
        cfl_violation: bool,
        divergence: bool,
        ctrl: BaseSecondaryController,
        ctrl_name: str,
        neg_mode: Optional[str]
    ) -> Dict[str, Any]:
        """Calcula el vector de KPIs riguroso y evalúa los Gates G1-G8."""
        t_arr = df["time"].to_numpy()
        f_arr = df["f_mean"].to_numpy()
        v_arr = df["V_mean"].to_numpy()
        e_f_arr = df["error_f"].to_numpy()
        e_v_arr = df["error_V"].to_numpy()
        diff_q = df["eta_Q_diff"].to_numpy()
        diff_p = df["eta_P_diff"].to_numpy()

        # Determinar el escalón inicial de perturbación |Delta f_step|
        mask_step = (t_arr >= t_event) & (t_arr <= t_event + 2.0)
        step_f = float(np.max(e_f_arr[mask_step])) if np.any(mask_step) else 0.4667

        # 1. Tiempo de asentamiento normativo (|e_f| <= freq_tolerance_hz, Energies eq. 11)
        # Este es el valor canónico vinculado a G1 (D-12)
        norm_bands = self.cfg.get("normative_bands", {}).get("secondary_control", {})
        f_tol = float(norm_bands.get("freq_tolerance_hz", 0.100))
        settling_bands = self.cfg.get("reporting", {}).get("step_settling_bands", [0.10, 0.05, 0.02])

        if not (divergence or neg_mode == "N1"):
            t_s_norm = calculate_settling_time(t_arr, e_f_arr, tolerance_abs=f_tol, t_start=t_event)
            # Bandas relativas al escalón leídas de bench_8nodos.yaml (S4)
            t_s_10 = calculate_settling_time(t_arr, e_f_arr, band_pct=float(settling_bands[0]), step_size=step_f, t_start=t_event)
            t_s_05 = calculate_settling_time(t_arr, e_f_arr, band_pct=float(settling_bands[1]), step_size=step_f, t_start=t_event)
            t_s_02 = calculate_settling_time(t_arr, e_f_arr, band_pct=float(settling_bands[2]), step_size=step_f, t_start=t_event)
        else:
            t_s_norm = None
            t_s_10 = None
            t_s_05 = None
            t_s_02 = None

        # 2. Rizado pico a pico en régimen permanente
        t_ss_start = max(t_event, duration - 20.0)
        delta_f_pp = calculate_peak_to_peak(f_arr, t_arr, t_ss_start)

        # 3. Dispersión en reparto estacionario (D-14)
        mask_ss = t_arr >= t_ss_start
        max_diff_q = float(np.mean(diff_q[mask_ss])) if np.any(mask_ss) else 0.0
        max_diff_p = float(np.mean(diff_p[mask_ss])) if np.any(mask_ss) else 0.0

        # 4. Errores en estado estacionario
        max_e_v = float(np.mean(e_v_arr[mask_ss])) if np.any(mask_ss) else 0.0
        max_e_w = float(np.mean(e_f_arr[mask_ss])) if np.any(mask_ss) else 0.0

        # Dinámica y calidad
        nadir_f = float(np.min(f_arr))
        rocof_val = calculate_rocof(f_arr, t_arr)
        rmse_f = calculate_rmse(f_arr, self.f_nom)
        rmse_v = calculate_rmse(v_arr, self.v_nom_pu)
        iae_f = calculate_iae(e_f_arr[t_arr >= t_event], self.dt)

        # 5. Condición CFL analítica (S4)
        cfl_stable = (cfl_number < 1.0) and (not cfl_violation) and (not divergence)

        # 6. Tolerancia a retardo de red tau_crit analítica (D-18 Opción C, S2, S3)
        tau_crit_ms, tau_crit_desc = self._compute_tau_crit(ctrl, ctrl_name, neg_mode, divergence)

        metrics_dict = {
            "controller": ctrl_name,
            "negative_control_mode": neg_mode,
            "t_s_norm": t_s_norm,
            "t_s_10_pct": t_s_10,
            "t_s_05_pct": t_s_05,
            "t_s_02_pct": t_s_02,
            "delta_f_pp": delta_f_pp,
            "max_diff_eta_Q": max_diff_q,
            "max_diff_eta_P": max_diff_p,
            "max_e_V_pu": max_e_v,
            "max_e_omega_hz": max_e_w,
            "nadir_f_hz": nadir_f,
            "rocof_hz_s": rocof_val,
            "rmse_f": rmse_f,
            "rmse_V": rmse_v,
            "iae_f": iae_f,
            "cfl_number": cfl_number,
            "cfl_stable": cfl_stable,
            "tau_crit_ms": tau_crit_ms,
            "tau_crit_details": tau_crit_desc,
            "total_messages": int(df["messages_sent"].iloc[-1]),
            "total_bytes": int(df["bytes_transferred"].iloc[-1]),
            "divergence": divergence
        }

        # Evaluar gates
        gates_eval = evaluate_gates(metrics_dict, self.cfg.get("acceptance_gates", {}))
        metrics_dict["gates"] = gates_eval
        metrics_dict["all_gates_passed"] = all(g["passed"] is True for g in gates_eval.values() if g["passed"] is not None)

        return metrics_dict
