import os
import sys
import math
import cmath
import csv
import time
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Central_PC.power_flow_fbs import ForwardBackwardSweepSolver
from Agents.node_dynamic_process import NodeDynamicProcess
from Agents.fixed_time_consensus import FixedTimeConsensusAgent


class SixNodeConsensusValidationRunner:
    """
    Ejecutor de prueba para validar la teoría de consenso en tiempo fijo (FxTS)
    y la recuperación secundaria de consignas de tensión y frecuencia en una
    microrred de 6 nodos en Baja Tensión (BT - 400V).
    
    Topología:
      - Nodo 1: Generador Diésel (Slack en isla, Líder V y ω)
      - Nodo 2: Solar PV (Fuente No Convencional)
      - Nodo 3: BESS (Sistema de Almacenamiento en Baterías)
      - Nodo 4: Carga Residencial (Demanda A)
      - Nodo 5: Carga Comercial   (Demanda B)
      - Nodo 6: Carga Industrial  (Demanda C)
    """

    def __init__(
        self,
        topology_path: str = None,
        output_csv: str = "output_data/test_6nodes_consensus_recovery.csv",
        v_base: float = 400.0,
        s_base: float = 10000.0,
        dt: float = 0.5,
        H_sys: float = 6.0,      # Inercia virtual del sistema (Swing Eq.) [s]
        D_sys: float = 12.0,     # Amortiguamiento de frecuencia [pu/pu]
        K_omega: float = 0.3,    # Ganancia integral del acumulador omega_offset
        K_v: float = 1.0,        # Ganancia integral del acumulador V_offset
        tau_lpf: float = 2.0,    # Constante de tiempo del LPF sobre P_net [s]
        K_p_freq: float = 400.0, # Ganancia proporcional de restauración de frecuencia a potencia [W/(rad/s)]
        K_i_freq: float = 250.0  # Ganancia integral de restauración de frecuencia a potencia [W/(rad/s*s)]
    ):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.topology_path = topology_path or os.path.join(base_dir, "config", "topologia_BT_6nodos.csv")
        self.output_csv = os.path.abspath(os.path.join(base_dir, output_csv))
        os.makedirs(os.path.dirname(self.output_csv), exist_ok=True)

        self.v_base = float(v_base)
        self.s_base = float(s_base)
        self.dt = float(dt)
        self.H_sys = float(H_sys)
        self.D_sys = float(D_sys)
        self.K_omega = float(K_omega)
        self.K_v = float(K_v)
        self.tau_lpf = float(tau_lpf)
        self.K_p_freq = float(K_p_freq)
        self.K_i_freq = float(K_i_freq)
        self.int_freq_error = 0.0

        # 1. Solucionador FBS en Baja Tensión
        self.solver = ForwardBackwardSweepSolver(V_base=self.v_base, S_base=self.s_base)
        self.solver.load_topology(self.topology_path)
        self.solver.set_operating_mode("OFFLINE", slack_node=1, V_slack=1.0)

        # 2. Procesos Dinámicos Físicos (1 kHz)
        self.proc_diesel = NodeDynamicProcess(node_id=1, source_type="DIESEL")
        self.proc_solar  = NodeDynamicProcess(node_id=2, source_type="SOLAR")
        self.proc_bess   = NodeDynamicProcess(node_id=3, source_type="BESS")

        # Desactivar droop primario del Diésel: en este ensayo de co-simulación distribuida la
        # regulación de frecuencia está a cargo del control secundario FxTS.
        # El droop default (m_p=6.283e-5) está calibrado para 50 kW nominal y satura P_target=0
        # ante cualquier desvío de ±1 Hz en una planta de 10 kW, generando oscilaciones inter-paso.
        self.proc_diesel.model.droop_enabled = False

        # Capacidades nominales de convertidores
        self.q_max = {1: 6000.0, 2: 3000.0, 3: 3000.0}
        self.p_max = {1: 10000.0, 2: 5000.0, 3: 5000.0}

        # 3. Agentes de Consenso FxTS (4 canales: V, Q, omega, P)
        self.agent_1 = FixedTimeConsensusAgent(agent_id=1, Q_max=self.q_max[1], P_max=self.p_max[1], mode="OFFLINE", c1=0.25, c2=0.15)
        self.agent_2 = FixedTimeConsensusAgent(agent_id=2, Q_max=self.q_max[2], P_max=self.p_max[2], mode="OFFLINE", c1=0.25, c2=0.15)
        self.agent_3 = FixedTimeConsensusAgent(agent_id=3, Q_max=self.q_max[3], P_max=self.p_max[3], mode="OFFLINE", c1=0.25, c2=0.15)

        # Topología del grafo de comunicación:
        # Nodos 1 y 3 (Despachables) están interconectados directamente para consenso de P.
        # Nodos 1, 2 y 3 están interconectados para soporte de tensión y consenso de Q.
        self.agent_1.set_adjacency({2: 1.0, 3: 1.0})
        self.agent_2.set_adjacency({1: 1.0, 3: 1.0})
        self.agent_3.set_adjacency({1: 1.0, 2: 1.0})

        # Cargar perfiles de demanda sintéticos
        base_forms = os.path.join(base_dir, "Forms")
        ensayos_dir = os.path.join(base_forms, "ensayos_red_hil")
        legacy_dir = os.path.join(base_forms, "formatos")
        formatos_dir = ensayos_dir if os.path.exists(ensayos_dir) else legacy_dir

        self.demanda_A = self._load_demanda_csv(os.path.join(formatos_dir, "datos_demanda_A.csv"))
        self.demanda_B = self._load_demanda_csv(os.path.join(formatos_dir, "datos_demanda_B.csv"))
        self.demanda_C = self._load_demanda_csv(os.path.join(formatos_dir, "datos_demanda_C.csv"))

        # Estados de control y acumuladores integradores secundarios
        self.Q_refs = {1: 1500.0, 2: 600.0, 3: 800.0}
        self.P_refs = {1: 3500.0, 2: 2500.0, 3: 1500.0}
        self.V_offsets = {1: 0.0, 2: 0.0, 3: 0.0}
        self.omega_offsets = {1: 0.0, 2: 0.0, 3: 0.0}
        self.f_sys = 60.0
        self.prev_theta_rad = {i: 0.0 for i in range(1, 7)}

    def _load_demanda_csv(self, file_path):
        data = []
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
                if not lines:
                    return data
                delim = ";" if ";" in lines[0] else ","
                reader = csv.reader(lines, delimiter=delim)
                header = [h.strip() for h in next(reader, [])]
                p_idx = header.index("P_kW") if "P_kW" in header else (header.index("P") if "P" in header else 1)
                q_idx = header.index("Q_kvar") if "Q_kvar" in header else (header.index("Q") if "Q" in header else 2)

                for row in reader:
                    if len(row) > max(p_idx, q_idx):
                        try:
                            p_w = float(row[p_idx].replace(",", ".")) * 1000.0
                            q_var = float(row[q_idx].replace(",", ".")) * 1000.0
                            data.append((p_w, q_var))
                        except ValueError:
                            continue
        return data

    def run(self, max_steps: int = 120):
        """
        Ejecuta la co-simulación durante max_steps (default 120 pasos = 60 segundos).
        """
        print("=" * 75)
        print(" ENSAYO EXPERIMENTAL: CONSENSO FxTS Y RECUPERACIÓN DE CONSIGNAS")
        print(f" - Topología:        {os.path.basename(self.topology_path)} (6 Nodos, BT 400V)")
        print(f" - Duración:         {max_steps} pasos ({max_steps * self.dt:.1f} s)")
        print(f" - Grafo de Consenso: N1(Diésel-Líder) <-> N2(Solar) <-> N3(BESS)")
        print(f" - Archivo Salida:   {self.output_csv}")
        print(f" - Swing Eq.:        H_sys={self.H_sys:.1f}s, D_sys={self.D_sys:.1f}, tau_lpf={self.tau_lpf:.1f}s")
        print(f" - Control Sec.:     K_omega={self.K_omega:.2f}, K_v={self.K_v:.2f}")
        print("=" * 75)

        headers = [
            "step", "time_sec", "f_sys_hz", "P_net_kW",
            "V1_pu", "V2_pu", "V3_pu", "V4_pu", "V5_pu", "V6_pu",
            "f1_hz", "f2_hz", "f3_hz", "f4_hz", "f5_hz", "f6_hz",
            "theta1_deg", "theta2_deg", "theta3_deg", "theta4_deg", "theta5_deg", "theta6_deg",
            "P1_kW", "P2_kW", "P3_kW", "P_dem_total_kW",
            "Q1_kvar", "Q2_kvar", "Q3_kvar", "Q_dem_total_kvar",
            "Q_ratio_1", "Q_ratio_2", "Q_ratio_3",
            "P_ratio_1", "P_ratio_2", "P_ratio_3",
            "V_offset_1", "V_offset_2", "V_offset_3",
            "omega_offset_1", "omega_offset_2", "omega_offset_3",
            "error_Q_12", "error_Q_23", "error_P_13", "error_V_ref"
        ]

        with open(self.output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

        voltages_dict = {i: 1.0 for i in range(1, 7)}
        start_wall = time.perf_counter()

        for step in range(1, max_steps + 1):
            t_sec = step * self.dt
            idx = step - 1

            # 1. Obtener demanda de cada nodo
            # Inyección de perturbación a los 25 s (paso 50): escalón de carga adicional (+35%)
            mult_demanda = 1.35 if t_sec >= 25.0 else 1.0
            p4_base, q4_base = self.demanda_A[idx % len(self.demanda_A)] if self.demanda_A else (2850.0, 936.0)
            p5_base, q5_base = self.demanda_B[idx % len(self.demanda_B)] if self.demanda_B else (1960.0, 398.0)
            p6_base, q6_base = self.demanda_C[idx % len(self.demanda_C)] if self.demanda_C else (1470.0, 298.0)

            P4, Q4 = p4_base * mult_demanda, q4_base * mult_demanda
            P5, Q5 = p5_base * mult_demanda, q5_base * mult_demanda
            P6, Q6 = p6_base * mult_demanda, q6_base * mult_demanda

            # 2. Paso de dinámica física con compensación de offsets secundarios
            v1_eff = (voltages_dict[1] + self.V_offsets[1]) * self.v_base
            v2_eff = (voltages_dict[2] + self.V_offsets[2]) * self.v_base
            v3_eff = (voltages_dict[3] + self.V_offsets[3]) * self.v_base

            # En paso >= 40 s (paso 80): caída solar del 40% (nubosidad)
            if t_sec >= 40.0:
                self.proc_solar.model.POA = 550.0

            out_diesel = self.proc_diesel.step_macro(
                V_pcc=v1_eff, Q_ref=self.Q_refs[1], P_ref=self.P_refs[1], delta_omega=self.omega_offsets[1], macro_dt=self.dt
            )
            out_solar = self.proc_solar.step_macro(
                V_pcc=v2_eff, Q_ref=self.Q_refs[2], P_ref=self.P_refs[2], delta_omega=self.omega_offsets[2], macro_dt=self.dt
            )
            out_bess = self.proc_bess.step_macro(
                V_pcc=v3_eff, Q_ref=self.Q_refs[3], P_ref=self.P_refs[3], delta_omega=self.omega_offsets[3], macro_dt=self.dt
            )

            P1, Q1 = out_diesel["P_w"], out_diesel["Q_var"]
            P2, Q2 = out_solar["P_w"],  out_solar["Q_var"]
            P3, Q3 = out_bess["P_w"],   out_bess["Q_var"]

            # Ratios de utilización
            q_ratio_1 = Q1 / self.q_max[1]
            q_ratio_2 = Q2 / self.q_max[2]
            q_ratio_3 = Q3 / self.q_max[3]

            p_ratio_1 = P1 / self.p_max[1]
            p_ratio_2 = P2 / self.p_max[2]
            p_ratio_3 = P3 / self.p_max[3]

            # 3. Intercambio P2P y Actualización de Consenso FxTS (4 Canales)
            omega_local = 2.0 * math.pi * self.f_sys
            states = {
                1: {"V": voltages_dict[1], "Q_ratio": q_ratio_1, "omega": omega_local, "P_ratio": p_ratio_1},
                2: {"V": voltages_dict[2], "Q_ratio": q_ratio_2, "omega": omega_local, "P_ratio": p_ratio_2},
                3: {"V": voltages_dict[3], "Q_ratio": q_ratio_3, "omega": omega_local, "P_ratio": p_ratio_3}
            }

            # Desacoplamiento de potencia activa para fuentes no despachables (Solar MPPT):
            # Para evitar que el inversor solar arrastre a los generadores despachables hacia
            # cero (madrugada) o sobregeneración masiva (mediodía), el intercambio de P_ratio
            # se neutraliza con el nodo 2, mientras que el Diésel (1) y el BESS (3) alcanzan
            # consenso de reparto de activa directamente entre sí.
            neighbor_states_1 = {
                2: {"V": states[2]["V"], "Q_ratio": states[2]["Q_ratio"], "omega": omega_local, "P_ratio": p_ratio_1},
                3: states[3]
            }
            neighbor_states_2 = {
                1: states[1],
                3: states[3]
            }
            neighbor_states_3 = {
                1: states[1],
                2: {"V": states[2]["V"], "Q_ratio": states[2]["Q_ratio"], "omega": omega_local, "P_ratio": p_ratio_3}
            }

            dV1, dQ1, dw1, dP1 = self.agent_1.update_consensus(
                voltages_dict[1], Q1, omega_i=omega_local, P_i=P1, neighbor_states=neighbor_states_1, dt=self.dt, return_all=True
            )
            dV2, dQ2, dw2, dP2 = self.agent_2.update_consensus(
                voltages_dict[2], Q2, omega_i=omega_local, P_i=P2, neighbor_states=neighbor_states_2, dt=self.dt, return_all=True
            )
            dV3, dQ3, dw3, dP3 = self.agent_3.update_consensus(
                voltages_dict[3], Q3, omega_i=omega_local, P_i=P3, neighbor_states=neighbor_states_3, dt=self.dt, return_all=True
            )

            # 4. Actualización con Acción Integral y Saturadores de Seguridad
            # a) Consignas de Reactiva Q_ref (Reparto proporcional de soporte de tensión)
            self.Q_refs[1] = max(0.0, min(self.q_max[1], self.Q_refs[1] + dQ1))
            self.Q_refs[2] = max(0.0, min(self.q_max[2], self.Q_refs[2] + dQ2))
            self.Q_refs[3] = max(0.0, min(self.q_max[3], self.Q_refs[3] + dQ3))

            # b) Lazo Restaurativo Secundario de Frecuencia hacia Potencia Activa (Control PI)
            # El error angular de frecuencia respecto a nominal (e_w = omega_nom - omega_sys)
            # comanda la potencia activa de recuperación necesaria para balancear la carga neta.
            err_w = (2.0 * math.pi * 60.0) - omega_local
            self.int_freq_error = max(-20.0, min(20.0, self.int_freq_error + err_w * self.dt))
            delta_P_restore = self.K_p_freq * err_w + self.K_i_freq * self.int_freq_error

            # Factores de participación por capacidad de generación despachable:
            # Diésel (10 kW) = 2/3 (66.7%), BESS (5 kW) = 1/3 (33.3%)
            p_disp_total = self.p_max[1] + self.p_max[3]
            gamma_1 = self.p_max[1] / p_disp_total
            gamma_3 = self.p_max[3] / p_disp_total

            # Despacho base adaptable con la demanda nominal esperada
            p_base_1 = 3500.0 * mult_demanda
            p_base_3 = 1750.0 * mult_demanda

            # Consignas de Activa P_ref: Despacho base + Restauración de frecuencia + Consenso P
            self.P_refs[1] = max(0.0, min(self.p_max[1], p_base_1 + gamma_1 * delta_P_restore + dP1))
            self.P_refs[3] = max(0.0, min(self.p_max[3], p_base_3 + gamma_3 * delta_P_restore + dP3))

            # c) Offsets integradores de Tensión V_offset (±10% p.u.) con ganancia K_v
            self.V_offsets[1] = max(-0.10, min(0.10, self.V_offsets[1] + self.K_v * dV1))
            self.V_offsets[2] = max(-0.10, min(0.10, self.V_offsets[2] + self.K_v * dV2))
            self.V_offsets[3] = max(-0.10, min(0.10, self.V_offsets[3] + self.K_v * dV3))

            # d) Offsets integradores de Frecuencia omega_offset para gobernadores
            self.omega_offsets[1] = max(-1.0, min(1.0, self.omega_offsets[1] + self.K_omega * dw1))
            self.omega_offsets[3] = max(-1.0, min(1.0, self.omega_offsets[3] + self.K_omega * dw3))
            self.omega_offsets[2] = 0.0

            # 5. Resolver Flujo de Potencia FBS en la Red
            P_inj = {1: P1, 2: P2, 3: P3, 4: -P4, 5: -P5, 6: -P6}
            Q_inj = {1: Q1, 2: Q2, 3: Q3, 4: -Q4, 5: -Q5, 6: -Q6}

            voltages_complex, conv, iters = self.solver.solve(P_inj, Q_inj)
            thetas_deg = {}
            f_nodes = {}
            for n in range(1, 7):
                v_c = voltages_complex.get(n, 1.0 + 0.0j)
                voltages_dict[n] = abs(v_c)
                th_rad = cmath.phase(v_c)
                thetas_deg[n] = math.degrees(th_rad)

                if n in (1, 2, 3):
                    # Frecuencia estimada por el lazo SRF-PLL / gobernador del inversor/generador
                    gen_out = {1: out_diesel, 2: out_solar, 3: out_bess}[n]
                    f_nodes[n] = float(gen_out.get("Fsys", self.f_sys))
                else:
                    # Frecuencia local en barra de carga derivada de la variación angular d_theta/dt
                    d_th = th_rad - self.prev_theta_rad[n]
                    d_th = (d_th + math.pi) % (2.0 * math.pi) - math.pi
                    f_nodes[n] = self.f_sys + d_th / (2.0 * math.pi * self.dt)

                self.prev_theta_rad[n] = th_rad

            # 6. Dinámica de Frecuencia del Sistema (Swing Equation sintonizada con LPF)
            self.f_sys, p_net_w = self.solver.compute_frequency_dynamics(
                P_inj, f_prev=self.f_sys, dt=self.dt, H_sys=self.H_sys, D_sys=self.D_sys, f_nom=60.0, tau_lpf=self.tau_lpf
            )

            # Métricas
            err_q_12 = abs(q_ratio_1 - q_ratio_2)
            err_q_23 = abs(q_ratio_2 - q_ratio_3)
            err_p_13 = abs(p_ratio_1 - p_ratio_3)
            err_v_ref = abs(voltages_dict[1] - 1.0)

            p_dem_total_kw = (P4 + P5 + P6) / 1000.0
            q_dem_total_kvar = (Q4 + Q5 + Q6) / 1000.0
            v_pu = [voltages_dict[i] for i in range(1, 7)]

            row = [
                step, round(t_sec, 2), round(self.f_sys, 4), round(p_net_w / 1000.0, 2),
                *[round(x, 5) for x in v_pu],
                *[round(f_nodes[i], 4) for i in range(1, 7)],
                *[round(thetas_deg[i], 3) for i in range(1, 7)],
                round(P1 / 1000.0, 2), round(P2 / 1000.0, 2), round(P3 / 1000.0, 2), round(p_dem_total_kw, 2),
                round(Q1 / 1000.0, 2), round(Q2 / 1000.0, 2), round(Q3 / 1000.0, 2), round(q_dem_total_kvar, 2),
                round(q_ratio_1, 4), round(q_ratio_2, 4), round(q_ratio_3, 4),
                round(p_ratio_1, 4), round(p_ratio_2, 4), round(p_ratio_3, 4),
                round(self.V_offsets[1], 4), round(self.V_offsets[2], 4), round(self.V_offsets[3], 4),
                round(self.omega_offsets[1], 4), round(self.omega_offsets[2], 4), round(self.omega_offsets[3], 4),
                round(err_q_12, 4), round(err_q_23, 4), round(err_p_13, 4), round(err_v_ref, 4)
            ]

            with open(self.output_csv, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(row)

            # Consola cada 10 pasos (cada 5 s)
            if step % 10 == 0 or step == 1 or step == 50 or step == 80:
                f_min_n = min(f_nodes.values())
                f_max_n = max(f_nodes.values())
                print(f"[Paso {step:03d} | t={t_sec:5.1f}s] f_sys={self.f_sys:.3f}Hz (f_min={f_min_n:.3f}, f_max={f_max_n:.3f}) | "
                      f"V_min={min(v_pu):.4f}pu (dV={self.V_offsets[2]:+.4f}) | "
                      f"Q_ratios=({q_ratio_1:.3f}, {q_ratio_2:.3f}, {q_ratio_3:.3f}) | ErrQ={err_q_12:.3f}")

        elapsed = time.perf_counter() - start_wall
        print("=" * 75)
        print(f" SIMULACION COMPLETADA CON EXITO EN {elapsed:.2f} s")
        print(f" Telemetria guardada en: {self.output_csv}")
        print("=" * 75)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prueba de Validación de Consenso y Recuperación de Consignas")
    parser.add_argument("--steps", type=int, default=120, help="Pasos de simulación (120 = 60s @ 500ms)")
    parser.add_argument("--output-csv", default="output_data/test_6nodes_consensus_recovery.csv")
    parser.add_argument("--H-sys", type=float, default=6.0, help="Inercia virtual Swing Eq. [s] (default: 6.0)")
    parser.add_argument("--D-sys", type=float, default=12.0, help="Amortiguamiento Swing Eq. (default: 12.0)")
    parser.add_argument("--K-omega", type=float, default=0.3, help="Ganancia integral omega_offset (default: 0.3)")
    parser.add_argument("--K-v", type=float, default=1.0, help="Ganancia integral V_offset (default: 1.0)")
    parser.add_argument("--tau-lpf", type=float, default=2.0, help="Constante de tiempo LPF sobre P_net [s] (default: 2.0)")
    parser.add_argument("--k-p-freq", type=float, default=400.0, help="Ganancia proporcional restauración frecuencia [W/(rad/s)] (default: 400.0)")
    parser.add_argument("--k-i-freq", type=float, default=250.0, help="Ganancia integral restauración frecuencia [W/(rad/s*s)] (default: 250.0)")
    args = parser.parse_args()

    runner = SixNodeConsensusValidationRunner(
        output_csv=args.output_csv,
        H_sys=args.H_sys,
        D_sys=args.D_sys,
        K_omega=args.K_omega,
        K_v=args.K_v,
        tau_lpf=args.tau_lpf,
        K_p_freq=args.k_p_freq,
        K_i_freq=args.k_i_freq
    )
    runner.run(max_steps=args.steps)
