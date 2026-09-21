import unittest
import os
import sys
import math

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Agents.finite_time_consensus import FixedTimeConsensusAgent, FiniteTimeConsensusAgent
from Diesel.SistemaDiesel import SistemaDiesel
from BESS.SistemaBESS import SistemaBESS
from Agents.node_dynamic_process import NodeDynamicProcess
from Central_PC.master_clock_zmq import MasterClockZMQ


class TestFrequencyConsensus(unittest.TestCase):
    """Pruebas para la integración del control de frecuencia y reparto de potencia activa."""

    def test_backward_compatibility_2channels(self):
        """Verifica que la llamada sin parámetros de frecuencia sigue retornando exactamente 2 valores (dV, dQ)."""
        agent = FixedTimeConsensusAgent(agent_id=2, Q_max=40000.0, mode="ONLINE")
        agent.set_adjacency({1: 1.0})
        neighbors = {1: {"V": 1.0, "Q_ratio": 0.25}}
        
        result = agent.update_consensus(V_i=0.99, Q_i=10000.0, neighbor_states=neighbors)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        dV, dQ = result
        self.assertIsInstance(dV, float)
        self.assertIsInstance(dQ, float)

    def test_4channel_consensus_step_online(self):
        """Verifica que al suministrar omega_i o P_i se retornan los 4 canales (delta_V, delta_Q, delta_omega, delta_P)."""
        agent = FixedTimeConsensusAgent(agent_id=2, Q_max=40000.0, P_max=50000.0, mode="ONLINE")
        agent.set_adjacency({1: 1.0, 3: 1.0})

        neighbors = {
            1: {"V": 1.0, "Q_ratio": 0.30, "omega": 376.99, "P_ratio": 0.50},
            3: {"V": 0.98, "Q_ratio": 0.40, "omega": 376.80, "P_ratio": 0.60}
        }
        res = agent.update_consensus(
            V_i=0.99,
            Q_i=12000.0,
            omega_i=376.90,
            P_i=25000.0,
            neighbor_states=neighbors,
            dt=0.5
        )
        self.assertEqual(len(res), 4)
        dV, dQ, dW, dP = res
        self.assertIsInstance(dV, float)
        self.assertIsInstance(dQ, float)
        self.assertIsInstance(dW, float)
        self.assertIsInstance(dP, float)
        self.assertAlmostEqual(agent.delta_f, dW / (2.0 * math.pi), places=5)

    def test_frequency_consensus_leader_pinning_offline(self):
        """En modo OFFLINE, el agente Diésel (agente 1) fija la referencia nominal de frecuencia (60 Hz = 376.99 rad/s)."""
        agent_leader = FixedTimeConsensusAgent(
            agent_id=1,
            P_max=50000.0,
            mode="OFFLINE",
            f_ref=60.0
        )
        agent_leader.set_adjacency({2: 1.0})

        # Frecuencia local baja (59.8 Hz -> omega = 375.73 rad/s)
        omega_low = 2.0 * math.pi * 59.8
        neighbors = {2: {"V": 1.0, "Q_ratio": 0.20, "omega": omega_low, "P_ratio": 0.30}}

        dV, dQ, dW, dP = agent_leader.update_consensus(
            V_i=1.0,
            Q_i=10000.0,
            omega_i=omega_low,
            P_i=15000.0,
            neighbor_states=neighbors,
            dt=0.5
        )
        # El pinning restaurativo debe generar dW > 0 para subir la frecuencia hacia 60 Hz
        self.assertGreater(dW, 0.0, "El líder Diésel debe inyectar offset de frecuencia positivo ante sub-frecuencia")
        self.assertGreater(agent_leader.delta_f, 0.0)

    def test_active_power_proportional_sharing(self):
        """Verifica que dos generadores con diferentes ratios de potencia activa convergen hacia el consenso."""
        # Para muestreo discreto a dt=0.5s con topología no dirigida (lambda_max = 2),
        # la condición de estabilidad de Euler exige h * (c1 + c2) < 1.0 (Olfati-Saber & Murray).
        agent1 = FixedTimeConsensusAgent(agent_id=1, P_max=50000.0, c1=0.25, c2=0.25, mode="OFFLINE")
        agent2 = FixedTimeConsensusAgent(agent_id=2, P_max=25000.0, c1=0.25, c2=0.25, mode="OFFLINE")
        agent1.set_adjacency({2: 1.0})
        agent2.set_adjacency({1: 1.0})

        # Agente 1 está a 80% de carga (40 kW), Agente 2 está a 20% de carga (5 kW)
        P1 = 40000.0
        P2 = 5000.0

        for _ in range(25):
            s1 = {"V": 1.0, "Q_ratio": 0.2, "omega": 376.99, "P_ratio": P1 / agent1.P_max}
            s2 = {"V": 1.0, "Q_ratio": 0.2, "omega": 376.99, "P_ratio": P2 / agent2.P_max}

            _, _, _, dP1 = agent1.update_consensus(1.0, 10000.0, omega_i=376.99, P_i=P1, neighbor_states={2: s2}, dt=0.5)
            _, _, _, dP2 = agent2.update_consensus(1.0, 5000.0, omega_i=376.99, P_i=P2, neighbor_states={1: s1}, dt=0.5)

            P1 += dP1
            P2 += dP2

        ratio1 = P1 / agent1.P_max
        ratio2 = P2 / agent2.P_max
        self.assertAlmostEqual(ratio1, ratio2, delta=0.15,
                               msg=f"Los ratios de potencia activa deben converger: r1={ratio1:.3f}, r2={ratio2:.3f}")

    def test_diesel_primary_droop_response(self):
        """Verifica que el generador Diésel aumente su potencia ante una caída de frecuencia de red (Droop omega-P)."""
        diesel = SistemaDiesel(P_nominal=50000.0, m_p=6.283e-5, f_nom=60.0)
        
        # En condiciones nominales (Fsys = 60 Hz)
        out_nom = diesel.step(dt=0.001, V_pcc=230.0)
        p_nom = out_nom["P_target"]

        # Ante caída de frecuencia a 59.8 Hz (-0.2 Hz)
        diesel.contexto["Fsys"] = 59.8
        out_drop = diesel.step(dt=0.001, V_pcc=230.0)
        p_drop = out_drop["P_target"]

        self.assertGreater(p_drop, p_nom,
                           f"La potencia objetivo debe aumentar ante subfrecuencia: P_drop={p_drop:.1f} > P_nom={p_nom:.1f}")
        self.assertGreater(out_drop["P_droop"], 0.0)

    def test_bess_available_power_scaling_with_soc(self):
        """Verifica que el BESS limite su potencia disponible según el Estado de Carga (SoC)."""
        bess = SistemaBESS(SoC_inicial=0.80, modo="promedio")
        p_disp_high = bess.P_disponible
        self.assertGreater(p_disp_high, 0.0)

        # Si SoC cae al límite mínimo (<= 0.20)
        bess.contexto["SoC"] = 0.15
        p_disp_empty = bess.P_disponible
        self.assertEqual(p_disp_empty, 0.0, "La potencia disponible de descarga debe ser 0 con SoC <= 0.20")

        # Al dar setpoint de descarga con batería vacía, P_target debe saturar a 0
        out = bess.step(dt=0.001, V_pcc=110.0, setpoints={"P_ref_w": 5000.0})
        self.assertEqual(out["P_target"], 0.0)

    def test_decoupling_voltage_vs_frequency(self):
        """Verifica que variaciones en los canales de frecuencia y potencia activa no alteren los cálculos de tensión y reactiva."""
        agent = FixedTimeConsensusAgent(agent_id=2, Q_max=30000.0, P_max=50000.0, mode="ONLINE")
        agent.set_adjacency({1: 1.0})

        # Caso A: frecuencia normal
        neighbors_a = {1: {"V": 1.02, "Q_ratio": 0.40, "omega": 376.99, "P_ratio": 0.50}}
        dV_a, dQ_a, _, _ = agent.update_consensus(0.98, 9000.0, omega_i=376.99, P_i=20000.0, neighbor_states=neighbors_a, dt=0.5)

        # Caso B: perturbación severa de frecuencia y potencia en el vecino
        neighbors_b = {1: {"V": 1.02, "Q_ratio": 0.40, "omega": 370.00, "P_ratio": 0.90}}
        dV_b, dQ_b, _, _ = agent.update_consensus(0.98, 9000.0, omega_i=376.99, P_i=20000.0, neighbor_states=neighbors_b, dt=0.5)

        self.assertAlmostEqual(dV_a, dV_b, places=6, msg="El canal de tensión debe estar desacoplado de la frecuencia")
        self.assertAlmostEqual(dQ_a, dQ_b, places=4, msg="El canal de reactiva debe estar desacoplado de la potencia activa")

    def test_master_clock_frequency_dynamics_island(self):
        """Verifica que MasterClockZMQ en modo OFFLINE responda a desbalances de potencia activa alterando f_sys_hz."""
        top_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "topologia_BT_4nodos.csv"))
        master = MasterClockZMQ(top_file, mode="FBS", port_rep=5567, port_pub=5568)
        try:
            master.set_operating_mode("OFFLINE", slack_node=1, V_slack=1.0)
            
            # Caso 1: Sobrecarga en la microrred (demanda > generación -> P_net < 0)
            injections_deficit = {
                2: {"P": -25000.0, "Q": 0.0},
                4: {"P": -25000.0, "Q": 0.0}
            }
            res = master.run_step(injections_deficit)
            self.assertIn("f_sys_hz", res)
            self.assertIn("P_net_w", res)
            self.assertLess(res["f_sys_hz"], 60.0, "Ante déficit de generación neta, la frecuencia de isla debe descender")
        finally:
            master.close()


if __name__ == "__main__":
    unittest.main()
