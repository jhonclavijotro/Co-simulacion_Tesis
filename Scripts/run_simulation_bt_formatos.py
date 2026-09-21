import os
import sys
import math
import csv
import time
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Central_PC.power_flow_fbs import ForwardBackwardSweepSolver
from Agents.node_dynamic_process import NodeDynamicProcess
from Agents.finite_time_consensus import FixedTimeConsensusAgent
from mock_data.data_loader import MockDataLoader


class BTSimulationRunner:
    """
    Ejecutor de Co-Simulación para Microrred Radial de 6 Nodos en Baja Tensión (BT - 400V).
    
    Características:
      - Tensión Base: 400 V (Línea-Línea), Potencia Base: 10 kVA (NTC 1340).
      - Nodo 1: Diésel (Slack en Isla, P_nom=10 kW, Q_max=6 kvar).
      - Nodo 2: Solar PV (Forms/formatos/datos_radiacion_temperatura.csv, P_nom=5 kW, Q_max=3 kvar).
      - Nodo 3: BESS (Forms/formatos/datos_vel_viento.csv o curva de carga, P_nom=3 kW, Q_max=2 kvar).
      - Nodo 4: Carga Residencial (Forms/formatos/datos_demanda_A.csv).
      - Nodo 5: Carga Comercial   (Forms/formatos/datos_demanda_B.csv).
      - Nodo 6: Carga Industrial  (Forms/formatos/datos_demanda_C.csv).
      - Algoritmo de Consenso en Tiempo Fijo (FxTS) para reparto proporcional de potencia reactiva Q.
      - Exportación de telemetría completa a CSV de alta resolución (paso 500 ms).
    """

    def __init__(
        self,
        topology_path: str = None,
        output_csv: str = "output_data/telemetry_monitor_formatos_bt.csv",
        v_base: float = 400.0,
        s_base: float = 10000.0,
        dt: float = 0.5
    ):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.topology_path = topology_path or os.path.join(base_dir, "config", "topologia_BT_6nodos.csv")
        self.output_csv = os.path.abspath(os.path.join(base_dir, output_csv))
        os.makedirs(os.path.dirname(self.output_csv), exist_ok=True)

        self.v_base = float(v_base)
        self.s_base = float(s_base)
        self.dt = float(dt)

        # 1. Solucionador de Red Radial FBS en Baja Tensión
        self.solver = ForwardBackwardSweepSolver(V_base=self.v_base, S_base=self.s_base)
        self.solver.load_topology(self.topology_path)
        self.solver.set_operating_mode("OFFLINE", slack_node=1, V_slack=1.0)

        # 2. Procesos Dinámicos DERs
        self.proc_diesel = NodeDynamicProcess(node_id=1, source_type="DIESEL")
        self.proc_solar  = NodeDynamicProcess(node_id=2, source_type="SOLAR")
        self.proc_bess   = NodeDynamicProcess(node_id=3, source_type="BESS")

        # 3. Agentes de Consenso FxTS para Reparto de Reactiva (Q-sharing)
        # Capacidades: Diésel=6 kvar, Solar=3 kvar, BESS=2 kvar
        self.q_max = {1: 6000.0, 2: 3000.0, 3: 2000.0}
        self.p_max = {1: 10000.0, 2: 5000.0, 3: 3000.0}

        self.agent_1 = FixedTimeConsensusAgent(agent_id=1, Q_max=self.q_max[1], P_max=self.p_max[1], mode="OFFLINE", c1=0.25, c2=0.15)
        self.agent_2 = FixedTimeConsensusAgent(agent_id=2, Q_max=self.q_max[2], P_max=self.p_max[2], mode="OFFLINE", c1=0.25, c2=0.15)
        self.agent_3 = FixedTimeConsensusAgent(agent_id=3, Q_max=self.q_max[3], P_max=self.p_max[3], mode="OFFLINE", c1=0.25, c2=0.15)

        # Topología de comunicación: 1 <-> 2 <-> 3
        self.agent_1.set_adjacency({2: 1.0})
        self.agent_2.set_adjacency({1: 1.0, 3: 1.0})
        self.agent_3.set_adjacency({2: 1.0})

        # 4. Cargar perfiles de demanda sintéticos de Formatos
        formatos_dir = os.path.join(base_dir, "Forms", "formatos")
        self.demanda_A = self._load_demanda_csv(os.path.join(formatos_dir, "datos_demanda_A.csv"))
        self.demanda_B = self._load_demanda_csv(os.path.join(formatos_dir, "datos_demanda_B.csv"))
        self.demanda_C = self._load_demanda_csv(os.path.join(formatos_dir, "datos_demanda_C.csv"))

        # Referencias de control iniciales (ratios desiguales para convergencia de consenso)
        self.Q_refs = {1: 1500.0, 2: 600.0, 3: 1000.0}
        self.P_refs = {1: 3000.0, 2: 2000.0, 3: 1000.0}
        self.f_sys = 60.0

    def _load_demanda_csv(self, file_path):
        data = []
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f, delimiter=";")
                next(reader, None)  # Cabecera: date;P;Q;S;Fp
                for row in reader:
                    if len(row) >= 3:
                        try:
                            # P y Q en kW y kvar en el CSV -> convertir a W y var
                            p_w = float(row[1].replace(",", ".")) * 1000.0
                            q_var = float(row[2].replace(",", ".")) * 1000.0
                            data.append((p_w, q_var))
                        except ValueError:
                            continue
        return data

    def run(self, max_steps: int = 240):
        print("=" * 70)
        print(" SIMULACIÓN COMPLETA MICRORRED BT (400V) - EVALUACIÓN 2 MINUTOS")
        print(f" - Topología:            {os.path.basename(self.topology_path)}")
        print(f" - Tensión Base:         {self.v_base} V (Baja Tensión)")
        print(f" - Potencia Base:        {self.s_base / 1000.0:.1f} kVA")
        print(f" - Duración:             {max_steps} pasos ({max_steps * self.dt:.1f} s / {max_steps * self.dt / 60:.1f} min)")
        print(f" - Muestras Demandas:    A={len(self.demanda_A)}, B={len(self.demanda_B)}, C={len(self.demanda_C)}")
        print(f" - Archivo de Salida:    {self.output_csv}")
        print("=" * 70)

        # Inicializar CSV con cabeceras estándar de tesis
        headers = [
            "step", "time_sec", "f_sys_hz", "P_net_kW",
            "V1_pu", "V2_pu", "V3_pu", "V4_pu", "V5_pu", "V6_pu",
            "V1_V", "V2_V", "V3_V", "V4_V", "V5_V", "V6_V",
            "Q_ratio_1", "Q_ratio_2", "Q_ratio_3",
            "error_Q_12", "error_Q_23", "error_V_12", "error_V_23"
        ]
        with open(self.output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

        voltages_dict = {i: 1.0 for i in range(1, 7)}
        start_wall = time.perf_counter()

        for step in range(1, max_steps + 1):
            t_sec = step * self.dt
            idx = step - 1

            # 1. Obtener demanda de cada nodo desde las series temporales de Formatos
            P4, Q4 = self.demanda_A[idx % len(self.demanda_A)] if self.demanda_A else (2850.0, 936.0)
            P5, Q5 = self.demanda_B[idx % len(self.demanda_B)] if self.demanda_B else (1960.0, 398.0)
            P6, Q6 = self.demanda_C[idx % len(self.demanda_C)] if self.demanda_C else (1470.0, 298.0)

            # 2. Paso de dinámica física para cada DER con la tensión de su nodo
            V1_volts = voltages_dict[1] * self.v_base
            V2_volts = voltages_dict[2] * self.v_base
            V3_volts = voltages_dict[3] * self.v_base

            out_diesel = self.proc_diesel.step_macro(V_pcc=V1_volts, Q_ref=self.Q_refs[1], P_ref=self.P_refs[1], macro_dt=self.dt)
            out_solar  = self.proc_solar.step_macro(V_pcc=V2_volts, Q_ref=self.Q_refs[2], P_ref=self.P_refs[2], macro_dt=self.dt)
            out_bess   = self.proc_bess.step_macro(V_pcc=V3_volts, Q_ref=self.Q_refs[3], P_ref=self.P_refs[3], macro_dt=self.dt)

            P1, Q1 = out_diesel["P_w"], out_diesel["Q_var"]
            P2, Q2 = out_solar["P_w"],  out_solar["Q_var"]
            P3, Q3 = out_bess["P_w"],   out_bess["Q_var"]

            # Ratios de potencia reactiva
            q_ratio_1 = Q1 / self.q_max[1]
            q_ratio_2 = Q2 / self.q_max[2]
            q_ratio_3 = Q3 / self.q_max[3]

            # 3. Consenso FxTS P2P para reparto de reactiva
            states = {
                1: {"V": voltages_dict[1], "Q_ratio": q_ratio_1, "omega": 2 * math.pi * self.f_sys},
                2: {"V": voltages_dict[2], "Q_ratio": q_ratio_2, "omega": 2 * math.pi * self.f_sys},
                3: {"V": voltages_dict[3], "Q_ratio": q_ratio_3, "omega": 2 * math.pi * self.f_sys}
            }

            _, dQ1, _, _ = self.agent_1.update_consensus(voltages_dict[1], Q1, {2: states[2]}, dt=self.dt, return_all=True)
            _, dQ2, _, _ = self.agent_2.update_consensus(voltages_dict[2], Q2, {1: states[1], 3: states[3]}, dt=self.dt, return_all=True)
            _, dQ3, _, _ = self.agent_3.update_consensus(voltages_dict[3], Q3, {2: states[2]}, dt=self.dt, return_all=True)

            self.Q_refs[1] = max(0.0, min(self.q_max[1], self.Q_refs[1] + dQ1))
            self.Q_refs[2] = max(0.0, min(self.q_max[2], self.Q_refs[2] + dQ2))
            self.Q_refs[3] = max(0.0, min(self.q_max[3], self.Q_refs[3] + dQ3))

            # 4. Inyecciones netas para el flujo de potencia FBS (Cargas consumen: signo negativo)
            P_inj = {
                1: P1,
                2: P2,
                3: P3,
                4: -P4,
                5: -P5,
                6: -P6
            }
            Q_inj = {
                1: Q1,
                2: Q2,
                3: Q3,
                4: -Q4,
                5: -Q5,
                6: -Q6
            }

            # 5. Resolver flujo de potencia Forward-Backward Sweep
            voltages_complex, conv, iters = self.solver.solve(P_inj, Q_inj)
            for n in range(1, 7):
                voltages_dict[n] = abs(voltages_complex.get(n, 1.0))

            # 6. Dinámica de frecuencia del sistema
            self.f_sys, p_net_w = self.solver.compute_frequency_dynamics(P_inj, f_prev=self.f_sys, dt=self.dt, f_nom=60.0)

            # Métricas de error y convergencia
            err_q_12 = abs(q_ratio_1 - q_ratio_2)
            err_q_23 = abs(q_ratio_2 - q_ratio_3)
            err_v_12 = abs(voltages_dict[1] - voltages_dict[2])
            err_v_23 = abs(voltages_dict[2] - voltages_dict[3])

            v_pu = [voltages_dict[i] for i in range(1, 7)]
            v_volts = [voltages_dict[i] * self.v_base for i in range(1, 7)]
            p_net_kw = p_net_w / 1000.0

            # 7. Registrar fila en CSV
            row = [
                step, round(t_sec, 2), round(self.f_sys, 4), round(p_net_kw, 2),
                *[round(x, 5) for x in v_pu],
                *[round(x, 2) for x in v_volts],
                round(q_ratio_1, 4), round(q_ratio_2, 4), round(q_ratio_3, 4),
                round(err_q_12, 4), round(err_q_23, 4),
                round(err_v_12, 5), round(err_v_23, 5)
            ]
            with open(self.output_csv, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(row)

            # Registro en consola cada 20 pasos (cada 10 segundos)
            if step % 20 == 0 or step == 1:
                p_dem_total = (P4 + P5 + P6) / 1000.0
                p_gen_total = (P1 + P2 + P3) / 1000.0
                print(f"[{step:03d}/{max_steps}] t={t_sec:5.1f}s | f={self.f_sys:.3f}Hz | Gen={p_gen_total:.2f}kW, Dem={p_dem_total:.2f}kW | "
                      f"Q_ratios=({q_ratio_1:.3f}, {q_ratio_2:.3f}, {q_ratio_3:.3f}) | Err_Q12={err_q_12:.4f} | Vmin={min(v_pu):.4f}pu")

        elapsed = time.perf_counter() - start_wall
        print("=" * 70)
        print(f" SIMULACIÓN DE 2 MINUTOS COMPLETADA EN {elapsed:.2f} s")
        print(f" Archivo generado: {self.output_csv}")
        print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulación Microrred BT con datos de Formatos")
    parser.add_argument("--steps", type=int, default=240, help="Número de pasos (240 = 2 minutos @ 500ms)")
    parser.add_argument("--output-csv", default="output_data/telemetry_monitor_formatos_bt.csv", help="Ruta archivo CSV")
    args = parser.parse_args()

    runner = BTSimulationRunner(output_csv=args.output_csv)
    runner.run(max_steps=args.steps)
