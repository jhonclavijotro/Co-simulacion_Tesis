import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Central_PC.sensitivity_matrices import SensitivityMatrixSolver
from Central_PC.master_clock_zmq import MasterClockZMQ
from GUI.gui_command_center import GUICommandCenter

class TestSensitivityMesh(unittest.TestCase):
    def setUp(self):
        self.top_radial = os.path.join(os.path.dirname(__file__), "..", "config", "topologia_BT_4nodos.csv")
        self.top_mallada = os.path.join(os.path.join(os.path.dirname(__file__), "..", "config", "topologia_BT_mallada_4nodos.csv"))

    def test_radial_vs_ring_zbus_solver(self):
        solver_radial = SensitivityMatrixSolver(mesh_type="RADIAL")
        solver_radial.load_topology(self.top_radial)
        
        solver_ring = SensitivityMatrixSolver(mesh_type="RING_ZBUS")
        solver_ring.load_topology(self.top_mallada)

        P_inj = {2: 10000.0, 4: -15000.0}
        Q_inj = {2: 2000.0, 4: -3000.0}

        v_radial, conv1, _ = solver_radial.solve(P_inj, Q_inj)
        v_ring, conv2, _ = solver_ring.solve(P_inj, Q_inj)

        self.assertTrue(conv1)
        self.assertTrue(conv2)

        # En una red anillada la caída de tensión en el nodo 4 debe ser menor que en la red radial sin retorno
        self.assertGreater(abs(v_ring[4]), abs(v_radial[4]))

    def test_mesh_type_switching(self):
        solver = SensitivityMatrixSolver(mesh_type="RADIAL")
        solver.load_topology(self.top_mallada)
        s_vp_radial_44 = solver.S_VP[(4, 4)]

        solver.set_mesh_type("RING_ZBUS")
        s_vp_ring_44 = solver.S_VP[(4, 4)]

        # En la matriz de impedancia Zbus reducida la autoimpedancia de barra 4 disminuye por los lazos en paralelo
        self.assertLess(s_vp_ring_44, s_vp_radial_44)

    def test_gui_command_center_mesh_type(self):
        cc = GUICommandCenter(topology_csv=self.top_mallada, mode="ONLINE", solver_mode="SENSITIVITY", mesh_type="RING_ZBUS")
        self.assertEqual(cc.mesh_type, "RING_ZBUS")
        
        history = cc.run_simulation(max_steps=1, port_rep=5598, port_pub=5599)
        self.assertEqual(len(history), 1)
        self.assertIn(1, history[0]["voltages"])
        self.assertIn(4, history[0]["voltages"])

if __name__ == "__main__":
    unittest.main()
