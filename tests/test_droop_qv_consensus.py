"""
Test de Regresión Permanente C3 (S-O-34 / D-34):
Droop Q-V y Excitación Reactiva en Banco IEEE 8 Nodos BT

Verifica rigurosamente los requisitos de C3:
1. Parámetros de Droop Q-V unificados para los 3 DERs:
   - Diésel (N1): m_q = 0.001333 V/var (Q_max = 6 kvar, Delta V = 8.0 V / 2.0%)
   - Solar (N2):  m_q = 0.002667 V/var (Q_max = 3 kvar, Delta V = 8.0 V / 2.0%)
   - BESS (N3):   m_q = 0.008000 V/var (Q_max = 1 kvar, Delta V = 8.0 V / 2.0%)
2. Respuesta física ante escalón reactivo de +1 kvar en Nodo 5 durante 5 s:
   - Dispersión de ratios e_Q > 0.010 durante la perturbación.
   - Retorno de e_Q <= 0.0067 (banda del 2%) en <= 13.5 s tras el cese.
   - e_Q != 0 en al menos 20 muestras bajo excitación.
   - Tensiones nodales acotadas estrictamente en [0.95, 1.05] pu en todos los nodos.
"""

import unittest
import numpy as np
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Central_PC.power_flow_fbs import ForwardBackwardSweepSolver
from Agents.fixed_time_consensus import FixedTimeConsensusAgent
from Agents.distributed_node_runner import DistributedNodeRunner


class TestDroopQVConsensus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topo_path = os.path.join(
            os.path.dirname(__file__), "..", "Forms", "escenarios_generados",
            "ESC-HIL-008_validacion_integrada", "topologia_red_8nodos.csv"
        )
        if not os.path.exists(cls.topo_path):
            cls.topo_path = os.path.join(os.path.dirname(__file__), "..", "config", "topologia_BT_8nodos.csv")

    def test_droop_slopes_and_capacities_c3(self):
        """Verifica que las pendientes m_q correspondan a una caída idéntica de 8.0 V a plena capacidad."""
        q_max = {1: 6000.0, 2: 3000.0, 3: 1000.0}
        delta_v_full = 8.0  # 2.0% de 400 V

        expected_mq = {
            1: delta_v_full / 6000.0,  # ~0.001333 V/var
            2: delta_v_full / 3000.0,  # ~0.002667 V/var
            3: delta_v_full / 1000.0,  # 0.008000 V/var
        }

        for n, q_m in q_max.items():
            runner = DistributedNodeRunner(
                node_id=n,
                source_type="DIESEL" if n == 1 else ("SOLAR" if n == 2 else "BESS"),
                master_host="127.0.0.1",
                p2p_port=18000 + n,
                q_max=q_m,
                v_base=400.0
            )
            try:
                self.assertAlmostEqual(runner.m_q, expected_mq[n], places=5,
                                       msg=f"Pendiente m_q incorrecta para Nodo {n}")
            finally:
                for s in (runner.sub_clock, runner.req_master, runner.pub_p2p, runner.sub_p2p):
                    try:
                        s.close(linger=0)
                    except Exception:
                        pass
                try:
                    runner.context.term()
                except Exception:
                    pass

    def test_reactive_step_excitation_and_reconvergence_c3(self):
        """
        Simula co-simulación física FBS de 80 s con escalón reactivo de +1 kvar en N5 (t=50..55s).
        Evalúa todos los criterios de aceptación de S-O-34 C3.
        """
        pf = ForwardBackwardSweepSolver(V_base=400.0, S_base=10000.0)
        pf.load_topology(self.topo_path)

        q_max = {1: 6000.0, 2: 3000.0, 3: 1000.0}
        m_q = {1: 8.0 / 6000.0, 2: 8.0 / 3000.0, 3: 8.0 / 1000.0}

        agents = {
            1: FixedTimeConsensusAgent(agent_id=1, Q_max=q_max[1], P_max=10000.0, mode='OFFLINE', c1=0.25, c2=0.15),
            2: FixedTimeConsensusAgent(agent_id=2, Q_max=q_max[2], P_max=5000.0, mode='OFFLINE', c1=0.25, c2=0.15),
            3: FixedTimeConsensusAgent(agent_id=3, Q_max=q_max[3], P_max=3000.0, mode='OFFLINE', c1=0.25, c2=0.15),
        }
        agents[1].set_adjacency({2: 1.0})
        agents[2].set_adjacency({1: 1.0, 3: 1.0})
        agents[3].set_adjacency({2: 1.0})

        delta_Q_sec = {1: 0.0, 2: 0.0, 3: 0.0}
        Q_actual = {1: 0.0, 2: 0.0, 3: 0.0}

        dt = 0.5
        t_end = 80.0
        steps = int(t_end / dt)

        t_history, e_Q_history, voltages_history = [], [], []

        P_load_base = {4: -1500.0, 5: -1000.0, 6: -2000.0, 7: -1200.0, 8: -800.0}
        Q_load_base = {4: -300.0, 5: -200.0, 6: -400.0, 7: -250.0, 8: -150.0}
        P_gen_base = {1: 4000.0, 2: 2000.0, 3: 500.0}

        for s in range(steps):
            t_s = s * dt
            # Perturbación física de reactiva: +1 kvar en N5 durante 5 s (t in [50, 55])
            Q_inj = Q_load_base.copy()
            if 50.0 <= t_s < 55.0:
                Q_inj[5] -= 1000.0

            P_inj = P_load_base.copy()
            for n in (2, 3):
                P_inj[n] = P_gen_base[n]
                Q_inj[n] = Q_actual[n]

            V_dict, conv, _ = pf.solve(P_inj, Q_inj, V_slack=1.0)
            self.assertTrue(conv, f"El solver FBS no convergió en el paso {s} (t={t_s}s)")

            # Balance en barra Slack asumido por generador Diésel (N1)
            Q_slack = -pf.Q_net
            Q_actual[1] = Q_slack

            V_volts = {n: abs(V_dict[n]) * 400.0 for n in V_dict}
            V_pu = {n: abs(V_dict[n]) for n in V_dict}
            voltages_history.append(V_pu)

            # Droop primario Q-V en inversores N2 y N3
            for n in (2, 3):
                q_droop = (400.0 - V_volts[n]) / m_q[n]
                Q_actual[n] = max(0.0, min(q_max[n], q_droop + delta_Q_sec[n]))

            # Ratios de potencia reactiva
            ratios = {n: Q_actual[n] / q_max[n] for n in (1, 2, 3)}
            e12 = abs(ratios[1] - ratios[2])
            e23 = abs(ratios[2] - ratios[3])
            e_Q = max(e12, e23)
            e_Q_history.append(e_Q)
            t_history.append(t_s)

            # Actualización del consenso FxTS
            states = {n: {'V': V_pu[n], 'Q_ratio': ratios[n], 'omega': 376.99, 'P_ratio': 0.5} for n in (1, 2, 3)}
            nbrs = {1: {2: states[2]}, 2: {1: states[1], 3: states[3]}, 3: {2: states[2]}}

            for n in (1, 2, 3):
                dV, dQ, dw, dP = agents[n].update_consensus(
                    V_i=V_pu[n],
                    Q_i=Q_actual[n],
                    omega_i=376.99,
                    P_i=P_gen_base.get(n, 4000.0),
                    eta_i=0.0,
                    neighbor_states=nbrs[n],
                    dt=dt,
                    return_all=True
                )
                delta_Q_sec[n] = max(-q_max[n], min(q_max[n], delta_Q_sec[n] + dQ))

        t_arr = np.array(t_history)
        eq_arr = np.array(e_Q_history)

        # Criterio 1: Dispersión de ratios e_Q > 0.010 durante la perturbación
        mask_pert = (t_arr >= 50.0) & (t_arr < 55.0)
        eq_pert_max = float(np.max(eq_arr[mask_pert]))
        self.assertGreater(eq_pert_max, 0.010,
                           f"e_Q máximo durante perturbación ({eq_pert_max:.4f}) no superó 0.010")

        # Criterio 2: Retorno a <= 0.0067 (2%) en <= 13.5 s tras cese (t=68.5 s)
        t_cessation = 55.0
        t_target = t_cessation + 13.5
        idx_13_5s = np.where(t_arr <= t_target)[0][-1]
        eq_at_13_5s = float(eq_arr[idx_13_5s])
        self.assertLessEqual(eq_at_13_5s, 0.0067,
                             f"e_Q a 13.5s tras cese ({eq_at_13_5s:.4f}) no retornó a <= 0.0067")

        # Criterio 3: e_Q != 0 en al menos 20 muestras bajo excitación
        mask_window = (t_arr >= 50.0) & (t_arr <= 70.0)
        n_nonzero_eq = int(np.sum(eq_arr[mask_window] > 0.001))
        self.assertGreaterEqual(n_nonzero_eq, 20,
                                f"Muestras con e_Q > 0.001 ({n_nonzero_eq}) fue menor a 20")

        # Criterio 4: Tensiones nodales en +-5% ([0.95, 1.05] pu)
        v_min_all = min(min(v.values()) for v in voltages_history)
        v_max_all = max(max(v.values()) for v in voltages_history)
        self.assertGreaterEqual(v_min_all, 0.95, f"Tensión mínima ({v_min_all:.4f} pu) violó límite 0.95 pu")
        self.assertLessEqual(v_max_all, 1.05, f"Tensión máxima ({v_max_all:.4f} pu) violó límite 1.05 pu")


if __name__ == "__main__":
    unittest.main()
