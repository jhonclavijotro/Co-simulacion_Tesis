import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Central_PC.power_flow_fbs import ForwardBackwardSweepSolver
from Scripts.cluster_deployer import ClusterDeployer
from Agents.distributed_node_runner import DistributedNodeRunner
from Agents.multi_load_process import MultiLoadProcess

class TestRadial13_8kVCluster(unittest.TestCase):

    def setUp(self):
        self.topo_csv = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "topologia_MT_13_8kV_6nodos.csv"))
        self.rpi_list_md = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "raspberry_list.md"))

    def test_topology_file_exists_and_valid(self):
        """Verifica que el archivo de topologia MT 13.8 kV exista y tenga los 6 nodos."""
        self.assertTrue(os.path.exists(self.topo_csv))
        solver = ForwardBackwardSweepSolver(V_base=13800.0, S_base=1000000.0)
        solver.load_topology(self.topo_csv)
        self.assertEqual(len(solver.nodes), 6)
        self.assertEqual(sorted(solver.nodes), [1, 2, 3, 4, 5, 6])
        self.assertEqual(len(solver.branches), 5)

    def test_island_mode_power_flow_solution(self):
        """Verifica que el flujo de potencia radial converja a 13.8 kV con Nodo 1 como Slack."""
        solver = ForwardBackwardSweepSolver(V_base=13800.0, S_base=1000000.0)
        solver.load_topology(self.topo_csv)
        solver.set_operating_mode("OFFLINE", slack_node=1, V_slack=1.0)

        # Inyecciones: Generacion DER (N2, N3) y Demandas (N4, N5, N6)
        P_inj = {
            2: 120000.0,   # Solar: 120 kW
            3: 40000.0,    # BESS: 40 kW
            4: -80000.0,   # Carga Residencial: -80 kW
            5: -60000.0,   # Carga Comercial: -60 kW
            6: -100000.0   # Carga Industrial: -100 kW
        }
        Q_inj = {
            2: 25000.0,
            3: 10000.0,
            4: -20000.0,
            5: -15000.0,
            6: -30000.0
        }
        voltages, conv, iters = solver.solve(P_inj, Q_inj)
        self.assertTrue(conv)
        self.assertLess(iters, 10)
        self.assertEqual(abs(voltages[1]), 1.0) # Slack node

        # Verificar que todas las tensiones permanezcan dentro de +/- 5% (0.95 a 1.05 pu)
        for n in [1, 2, 3, 4, 5, 6]:
            v_pu = abs(voltages[n])
            self.assertGreater(v_pu, 0.95)
            self.assertLess(v_pu, 1.05)

    def test_cluster_deployer_parsing(self):
        """Verifica que ClusterDeployer parsee raspberry_list.md como Fuente Unica de Verdad."""
        deployer = ClusterDeployer(list_path=self.rpi_list_md)
        self.assertEqual(len(deployer.nodes), 5)
        
        # Verificar mapeo de roles
        self.assertEqual(deployer.nodes[0]["ip"], "10.0.0.151")
        self.assertEqual(deployer.nodes[0]["role"], "DIESEL_SLACK")
        self.assertEqual(deployer.nodes[1]["ip"], "10.0.0.152")
        self.assertEqual(deployer.nodes[1]["role"], "SOLAR_PV")
        self.assertEqual(deployer.nodes[2]["ip"], "10.0.0.153")
        self.assertEqual(deployer.nodes[2]["role"], "BESS_STORAGE")
        self.assertEqual(deployer.nodes[3]["ip"], "10.0.0.154")
        self.assertEqual(deployer.nodes[3]["role"], "LOADS_TRIPLE")
        self.assertEqual(deployer.nodes[4]["ip"], "10.0.0.155")
        self.assertEqual(deployer.nodes[4]["role"], "MONITOR_NODE")


if __name__ == "__main__":
    unittest.main()
