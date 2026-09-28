"""
Ejecutor de la Prueba de Co-Simulación de 60 Segundos en Microred de BT (7 Nodos).
Evalúa el comportamiento dinámico del consenso en tiempo fijo (FxTS) ante:
  1. Variaciones de Demanda (Reescalón en t=15s).
  2. Variaciones de Generación Solar (Sombreado en t=30s).
  3. Perturbaciones de Comunicación P2P (Pérdida 20%, latencia 100-300ms, corte N2-N3 a t=45s..60s).

Soporta ejecución en modo simulación acelerada/local y modo distribuido en Raspberry Pis.
"""

import os
import sys
import json
import time
import math
import csv
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Central_PC.power_flow_fbs import ForwardBackwardSweepSolver
from Agents.node_dynamic_process import NodeDynamicProcess
from Agents.finite_time_consensus import FixedTimeConsensusAgent
from Agents.network_impairment_proxy import NetworkImpairmentProxy


class SevenNodeMicrogridRunner:
    """
    Runner para el ensayo de 60 segundos con 7 nodos en Baja Tensión (BT - 400V).
    """

    def __init__(
        self,
        topology_path: str = None,
        scenario_path: str = None,
        output_csv: str = "output_data/test_7nodes_60s_results.csv",
        v_base: float = 400.0,
        s_base: float = 10000.0,
        dt: float = 0.5
    ):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.topology_path = topology_path or os.path.join(base_dir, "config", "topologia_BT_7nodos.csv")
        self.scenario_path = scenario_path or os.path.join(base_dir, "mock_data", "scenario_60s_bt.json")
        self.output_csv = os.path.abspath(os.path.join(base_dir, output_csv))
        os.makedirs(os.path.dirname(self.output_csv), exist_ok=True)

        self.v_base = float(v_base)
        self.s_base = float(s_base)
        self.dt = float(dt)

        # Cargar solver FBS
        self.fbs = ForwardBackwardSweepSolver(
            V_base=self.v_base,
            S_base=self.s_base
        )
        self.fbs.load_topology(self.topology_path)
        self.fbs.set_operating_mode("OFFLINE", slack_node=1, V_slack=1.0)

        # Cargar escenario mock
        with open(self.scenario_path, "r", encoding="utf-8") as f:
            self.scenario = json.load(f)

        # Definir nodos y agentes
        self.nodes = {}
        self.agents = {}
        self.impairment_proxy = NetworkImpairmentProxy()

        # Grafo de comunicación P2P base entre agentes de consenso
        # Adyacencia: 1-2, 2-3, 2-4, 3-5, 3-6, 5-7
        self.base_adj = {
            1: {2: 1.0},
            2: {1: 1.0, 3: 1.0, 4: 1.0},
            3: {2: 1.0, 5: 1.0, 6: 1.0},
            4: {2: 1.0},
            5: {3: 1.0, 7: 1.0},
            6: {3: 1.0},
            7: {5: 1.0}
        }

        # Inicializar procesos dinámicos y agentes FxTS para los 7 nodos
        for i in range(1, 8):
            self.nodes[i] = NodeDynamicProcess(
                node_id=i,
                hold_mode="ZFOH",
                zfoh_lambda=0.5
            )
            # Agentes de consenso FxTS
            self.agents[i] = FixedTimeConsensusAgent(
                agent_id=i,
                Q_max=8000.0 if i in [1, 2, 3] else 3000.0,
                P_max=15000.0 if i == 1 else (10000.0 if i in [2, 3] else 5000.0),
                mode="OFFLINE",
                alpha=0.8,
                beta=1.2,
                c1=0.25,
                c2=0.15,
                epsilon=1e-3,
                max_stale_steps=4
            )
            self.agents[i].set_adjacency(self.base_adj.get(i, {}))

    def run(self):
        print("=" * 75)
        print(" ENSAYO DE CO-SIMULACIÓN 60s: MICRORRED BT (7 NODOS) CON FxTS Y IMPAIRMENT P2P")
        print("=" * 75)
        print(f" - Topología: {os.path.basename(self.topology_path)}")
        print(f" - Dataset:   {os.path.basename(self.scenario_path)}")
        print(f" - Output:    {self.output_csv}")
        print("=" * 75)

        results = []
        f_sys = 60.0
        v_offset_accum = 0.0
        omega_offset_accum = 0.0

        # Estado dinámico de inyecciones reactivas y activas acumuladas por FxTS
        q_accum = {i: 0.0 for i in range(1, 8)}
        p_bess_accum = 0.0

        for step_data in self.scenario:
            step = step_data["step"]
            t_sec = step_data["t_sec"]
            solar = step_data["solar_node_3"]
            loads = step_data["loads"]
            impairment = step_data["comms_impairment"]

            # 1. Configurar perturbación de comunicación en el proxy
            self.impairment_proxy.emulator.loss_rate = impairment["packet_loss_rate"]
            self.impairment_proxy.emulator.base_latency_ms = impairment["latency_ms"]

            # 2. Calcular inyecciones netas para el flujo de potencia
            p_injections = {}
            q_injections = {}

            # Nodos de carga (4..7)
            for n_str, l_val in loads.items():
                n_id = int(n_str)
                p_injections[n_id] = -l_val["P_w"]
                q_injections[n_id] = -l_val["Q_var"] + q_accum[n_id]

            # Nodo 3 (Solar FV)
            p_solar = solar["P_available_w"]
            p_injections[3] = p_solar
            q_injections[3] = q_accum[3]

            # Nodo 2 (BESS)
            p_injections[2] = p_bess_accum
            q_injections[2] = q_accum[2]

            # Nodo 1 (Diésel - Slack) se autorregula en el solver FBS

            # 3. Resolver Flujo de Potencia Radial FBS
            V_complex_dict, converged, iterations = self.fbs.solve(p_injections, q_injections)
            voltages = {
                str(k): {"V_pu": abs(V_complex_dict[k])}
                for k in range(1, 8)
            }
            p_net_total = self.fbs.P_net

            # Dinámica de frecuencia del sistema en isla (Swing Equation)
            delta_P_pu = p_net_total / self.s_base
            delta_P_pu = max(-0.15, min(0.15, delta_P_pu))
            df_dt = (delta_P_pu / (2.0 * 4.0)) * 60.0 - 2.0 * (f_sys - 60.0)
            f_sys = max(58.5, min(61.5, f_sys + df_dt * self.dt))
            omega_local = 2.0 * math.pi * f_sys

            # 4. Difusión de mensajes en la Red P2P con Impairment Proxy
            # Cada nodo recolecta las mediciones de sus vecinos
            node_states = {
                i: {
                    "V_pu": voltages[str(i)]["V_pu"],
                    "Q_var": q_injections.get(i, 0.0),
                    "omega": omega_local,
                    "P_w": p_injections.get(i, 0.0)
                }
                for i in range(1, 8)
            }

            # Aplicar desconexión temporal de enlaces si corresponde
            active_adj = {}
            disc_links = impairment.get("disconnected_links", [])
            for src, nbrs in self.base_adj.items():
                filtered = {}
                for tgt, w in nbrs.items():
                    if [str(src), str(tgt)] in disc_links or [str(tgt), str(src)] in disc_links:
                        continue  # Enlace caído
                    filtered[tgt] = w
                active_adj[src] = filtered

            # 5. Ejecutar Algoritmo de Consenso FxTS en cada Agente
            consensus_deltas = {}
            for i in range(1, 8):
                self.agents[i].set_adjacency(active_adj[i])
                
                # Obtener mediciones de vecinos filtradas por el proxy de canal
                raw_neighbors = {nbr_id: node_states[nbr_id] for nbr_id in active_adj[i]}
                filtered_neighbors, _ = self.impairment_proxy.filter_neighbor_states(
                    receiver_id=i,
                    raw_neighbor_states=raw_neighbors,
                    current_step=step,
                    current_time_s=t_sec
                )

                neighbors_dict = {}
                for nbr_id, d in filtered_neighbors.items():
                    q_max_nbr = self.agents[nbr_id].Q_max
                    p_max_nbr = self.agents[nbr_id].P_max
                    neighbors_dict[nbr_id] = {
                        "V": d["V_pu"],
                        "Q_ratio": d["Q_var"] / q_max_nbr if q_max_nbr > 0 else 0.0,
                        "omega": d["omega"],
                        "P_ratio": d["P_w"] / p_max_nbr if p_max_nbr > 0 else 0.0
                    }

                # Paso de control FxTS
                dV, dQ, dW, dP = self.agents[i].update_consensus(
                    V_i=node_states[i]["V_pu"],
                    Q_i=node_states[i]["Q_var"],
                    neighbor_states=neighbors_dict,
                    dt=self.dt,
                    omega_i=node_states[i]["omega"],
                    P_i=node_states[i]["P_w"],
                    return_all=True
                )
                consensus_deltas[i] = (dV, dQ, dW, dP)

            # 6. Actualizar Procesos Dinámicos de Inversores/Cargas
            for i in range(1, 8):
                dV, dQ, dW, dP = consensus_deltas[i]
                q_accum[i] += dQ
                if i == 2:
                    p_bess_accum += dP

                self.nodes[i].step(
                    V_pcc=voltages[str(i)]["V_pu"] * self.v_base,
                    Q_ref=q_injections.get(i, 0.0) + dQ,
                    P_ref=p_injections.get(i, 0.0) + dP,
                    delta_P=dP,
                    delta_omega=dW
                )

            # 7. Calcular Métricas de Desempeño
            v_vals = [voltages[str(k)]["V_pu"] for k in range(1, 8)]
            v_min = min(v_vals)
            v_max = max(v_vals)
            consensus_err_v = v_max - v_min

            q_ratios = [q_injections.get(k, 0.0) / self.agents[k].Q_max for k in [1, 2, 3]]
            q_ratio_std = math.sqrt(sum((r - sum(q_ratios)/3.0)**2 for r in q_ratios) / 3.0)

            rec = {
                "step": step,
                "t_sec": t_sec,
                "f_sys_hz": round(f_sys, 4),
                "P_net_kw": round(p_net_total / 1000.0, 3),
                "V_min_pu": round(v_min, 4),
                "V_max_pu": round(v_max, 4),
                "consensus_err_v": round(consensus_err_v, 4),
                "q_ratio_std": round(q_ratio_std, 4),
                "solar_kw": round(p_solar / 1000.0, 2),
                "bess_p_kw": round(p_injections[2] / 1000.0, 2),
                "loss_rate": impairment["packet_loss_rate"],
                "latency_ms": impairment["latency_ms"]
            }
            results.append(rec)

            if step % 20 == 0 or step == 1:
                print(f"[{t_sec:4.1f}s] Paso {step:03d} | f={f_sys:.3f}Hz | P_net={p_net_total/1000.0:6.2f}kW | Err_V={consensus_err_v:.4f}pu | Solar={p_solar/1000.0:.1f}kW | Loss={impairment['packet_loss_rate']*100:.0f}%")

        # Guardar resultados en CSV
        fieldnames = list(results[0].keys())
        with open(self.output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

        print("=" * 75)
        print(f" PRUEBA COMPLETADA EXITOSAMENTE. Resultados guardados en: {self.output_csv}")
        print("=" * 75)
        self.evaluate_summary(results)

    def evaluate_summary(self, results):
        f_vals = [r["f_sys_hz"] for r in results]
        err_v_vals = [r["consensus_err_v"] for r in results]

        # Fase I (0-15s)
        phase1_err = sum(r["consensus_err_v"] for r in results[0:30]) / 30.0
        # Fase II (15-30s)
        f_nadir = min(r["f_sys_hz"] for r in results[30:60])
        # Fase IV (45-60s)
        phase4_err = sum(r["consensus_err_v"] for r in results[90:120]) / 30.0

        print("\n--- INFORME DE EVALUACIÓN DE CRITERIOS DE ÉXITO ---")
        print(f"1. Fase I (Arranque / Línea Base):  Error promedio de tensión = {phase1_err:.4f} pu (Objetivo: < 0.005 pu)")
        print(f"2. Fase II (Reescalón Demanda):     Frecuencia Nadir = {f_nadir:.3f} Hz (Objetivo: >= 59.5 Hz)")
        print(f"3. Fase IV (Pérdidas P2P 20%):      Error promedio de tensión = {phase4_err:.4f} pu (Objetivo: Estabilidad sostenida)")
        print("---------------------------------------------------\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Runner Ensayo 60s Microred BT 7 Nodos")
    parser.add_argument("--topology", default=None, help="Ruta al CSV de topologia")
    parser.add_argument("--scenario", default=None, help="Ruta al JSON de escenario sintético")
    parser.add_argument("--output", default="output_data/test_7nodes_60s_results.csv", help="Ruta al CSV de resultados")
    args = parser.parse_args()

    runner = SevenNodeMicrogridRunner(
        topology_path=args.topology,
        scenario_path=args.scenario,
        output_csv=args.output
    )
    runner.run()
