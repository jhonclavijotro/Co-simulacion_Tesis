"""
Batería de pruebas unitarias y de integración para el Régimen Excedentario (Regime 2 / S-36).
Tesis de Grado: Control Secundario Distribuido en Tiempo Fijo (FxTS).

Verifica:
  1. BESS bidireccional: inyección con signo, absorción/carga (P < 0) e incremento de SoC.
  2. Acotamiento físico de P_charge_max y P_discharge_max según límites de SoC [0.20, 0.95].
  3. Recorte solar (curtailment) respecto al MPP disponible mediante curtail_ratio in [0, 1].
  4. Consenso FxTS de índice de excedente (eta_excess) entre BESS y Solar.
  5. Contratos de telemetría y ejecución en NodeDynamicProcess y DistributedNodeRunner.
"""

import unittest
import math
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from BESS.SistemaBESS import SistemaBESS
from Solar.SistemaSolar import SistemaSolar
from Agents.fixed_time_consensus import FixedTimeConsensusAgent
from Agents.node_dynamic_process import NodeDynamicProcess
from Agents.distributed_node_runner import DistributedNodeRunner


class TestSurplusRegime(unittest.TestCase):
    """Pruebas del régimen excedentario y control coordinado de sobregeneración."""

    def test_bess_bidirectional_charging_and_soc_increase(self):
        """Verifica que consignas de potencia negativa (P < 0) carguen la batería e incrementen el SoC."""
        bess = SistemaBESS(SoC_inicial=0.50, modo="promedio")
        soc_initial = float(bess.contexto["SoC"])
        self.assertAlmostEqual(soc_initial, 0.50, places=4)
        self.assertGreater(bess.P_charge_max, 0.0)

        # Inyectar consigna de carga de -3000 W durante 500 micro-pasos (0.5 s a dt=1ms)
        for _ in range(500):
            out = bess.step(dt=0.001, V_pcc=110.0, setpoints={"P_ref_w": -3000.0})

        self.assertLess(out["P_target"], 0.0, "P_target debe ser negativa para indicar absorción/carga")
        soc_final = float(bess.contexto["SoC"])
        self.assertGreater(soc_final, soc_initial, "El SoC debe haber aumentado tras el ciclo de carga")

    def test_bess_charge_limit_at_high_soc(self):
        """Verifica que el BESS bloquee la carga cuando el SoC alcanza o supera el 95%."""
        bess = SistemaBESS(SoC_inicial=0.96, modo="promedio")
        self.assertEqual(bess.P_charge_max, 0.0, "P_charge_max debe ser 0.0 si SoC >= 0.95")

        out = bess.step(dt=0.001, V_pcc=110.0, setpoints={"P_ref_w": -5000.0})
        self.assertEqual(out["P_target"], 0.0, "P_target de carga debe saturar a 0 si la batería está llena")

    def test_bess_discharge_limit_at_low_soc(self):
        """Verifica que el BESS bloquee la descarga cuando el SoC cae al 20% o menos."""
        bess = SistemaBESS(SoC_inicial=0.18, modo="promedio")
        self.assertEqual(bess.P_discharge_max, 0.0, "P_discharge_max debe ser 0.0 si SoC <= 0.20")

        out = bess.step(dt=0.001, V_pcc=110.0, setpoints={"P_ref_w": 5000.0})
        self.assertEqual(out["P_target"], 0.0, "P_target de descarga debe saturar a 0 si la batería está vacía")

    def test_solar_curtailment_execution(self):
        """Verifica que SistemaSolar reduzca la potencia inyectada proporcionalmente a curtail_ratio."""
        solar = SistemaSolar(N_inv=1)
        solar.POA = 1000.0
        solar.Tam = 298.15

        # 1. Operación normal a MPP (curtail_ratio = 1.0)
        out_mpp = solar.step(dt=0.001, V_pcc=110.0, setpoints={"curtail_ratio": 1.0})
        p_mpp = out_mpp["Pw"]
        self.assertGreater(p_mpp, 0.0)
        self.assertEqual(out_mpp["P_curtailed"], 0.0)
        self.assertEqual(out_mpp["curtail_ratio"], 1.0)

        # 2. Operación con 40% de recorte (curtail_ratio = 0.60 -> 60% de inyección)
        out_curtailed = solar.step(dt=0.001, V_pcc=110.0, setpoints={"curtail_ratio": 0.60})
        p_eff = out_curtailed["Pw"]
        p_mpp_curr = out_curtailed["P_mpp"]
        p_curt = out_curtailed["P_curtailed"]

        self.assertAlmostEqual(p_eff, p_mpp_curr * 0.60, places=3, msg="Potencia efectiva debe ser 60% del MPP actual")
        self.assertAlmostEqual(p_curt, p_mpp_curr * 0.40, places=3, msg="Potencia recortada debe ser 40% del MPP actual")
        self.assertAlmostEqual(out_curtailed["curtail_ratio"], 0.60, places=4)

    def test_fixed_time_excess_consensus_convergence(self):
        """Verifica que dos agentes con índices de excedente dispares converjan hacia un reparto equitativo."""
        agent_pv = FixedTimeConsensusAgent(agent_id=2, c1=0.25, c2=0.25, mode="OFFLINE")
        agent_bess = FixedTimeConsensusAgent(agent_id=3, c1=0.25, c2=0.25, mode="OFFLINE")

        agent_pv.set_adjacency({3: 1.0})
        agent_bess.set_adjacency({2: 1.0})

        # Inicialmente el solar está recortando al 90% (eta=0.9) y la batería apenas absorbiendo al 10% (eta=0.1)
        eta_pv = 0.90
        eta_bess = 0.10

        for _ in range(25):
            s_pv = {"eta_excess": eta_pv}
            s_bess = {"eta_excess": eta_bess}

            d_eta_pv = agent_pv.update_excess_consensus(eta_pv, neighbor_states={3: s_bess}, dt=0.5)
            d_eta_bess = agent_bess.update_excess_consensus(eta_bess, neighbor_states={2: s_pv}, dt=0.5)

            eta_pv = max(0.0, min(1.0, eta_pv + d_eta_pv))
            eta_bess = max(0.0, min(1.0, eta_bess + d_eta_bess))

        self.assertAlmostEqual(
            eta_pv, eta_bess, delta=0.10,
            msg=f"Los índices de exceso deben converger por consenso FxTS: eta_pv={eta_pv:.3f}, eta_bess={eta_bess:.3f}"
        )

    def test_node_dynamic_process_surplus_telemetry(self):
        """Verifica que NodeDynamicProcess exponga SoC, P_charge_max, P_discharge_max, P_curtailed y curtail_ratio."""
        proc_solar = NodeDynamicProcess(node_id=2, source_type="SOLAR")
        out_sol = proc_solar.step(V_pcc=400.0, curtail_ratio=0.75)
        self.assertIn("curtail_ratio", out_sol)
        self.assertIn("P_curtailed", out_sol)
        self.assertIn("P_mpp", out_sol)
        self.assertEqual(out_sol["curtail_ratio"], 0.75)

        proc_bess = NodeDynamicProcess(node_id=3, source_type="BESS")
        out_bess = proc_bess.step(V_pcc=400.0, P_ref=-2500.0)
        self.assertIn("SoC", out_bess)
        self.assertIn("P_charge_max", out_bess)
        self.assertIn("P_discharge_max", out_bess)
        self.assertLess(out_bess["P_w"], 0.0)

    def test_distributed_node_runner_surplus_configuration(self):
        """Verifica que DistributedNodeRunner soporte límites de carga y mínimo técnico de diesel."""
        runner_bess = DistributedNodeRunner(
            node_id=3,
            source_type="BESS",
            master_host="127.0.0.1",
            p2p_port=6410,
            port_rep=6411,
            port_pub=6412,
            p_charge_max=4500.0,
            p_min_diesel=1000.0
        )
        try:
            self.assertEqual(runner_bess.p_charge_max, 4500.0)
            self.assertEqual(runner_bess.p_min_diesel, 1000.0)
            self.assertEqual(runner_bess.curtail_ratio, 1.0)
            self.assertEqual(runner_bess.eta_excess, 0.0)
        finally:
            runner_bess.close()


if __name__ == "__main__":
    unittest.main()
