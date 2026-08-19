import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Central_PC.power_flow_fbs import ForwardBackwardSweepSolver
from Central_PC.sensitivity_matrices import SensitivityMatrixSolver

class TestPowerFlowSolvers(unittest.TestCase):

    def setUp(self):
        self.top_bt = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "topologia_BT_4nodos.csv"))
        self.top_mt = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "topologia_MT_Nnodos.csv"))

    def test_fbs_solver_bt(self):
        solver = ForwardBackwardSweepSolver(V_base=400.0, S_base=100000.0)
        n_nodes, n_br = solver.load_topology(self.top_bt)
        self.assertEqual(n_nodes, 4)
        self.assertEqual(n_br, 3)

        P_test = {2: 5000.0, 4: -10000.0}
        Q_test = {2: 1000.0, 4: -2000.0}

        V_res, converged, iters = solver.solve(P_test, Q_test)
        self.assertTrue(converged)
        self.assertLessEqual(iters, 20)
        self.assertAlmostEqual(abs(V_res[1]), 1.0, places=4)

    def test_sensitivity_solver_bt(self):
        solver = SensitivityMatrixSolver(V_base=400.0, S_base=100000.0)
        n_nodes = solver.load_topology(self.top_bt)
        self.assertEqual(n_nodes, 4)

        P_test = {2: 5000.0, 4: -10000.0}
        Q_test = {2: 1000.0, 4: -2000.0}

        V_res, converged, iters = solver.solve(P_test, Q_test)
        self.assertTrue(converged)
        self.assertAlmostEqual(abs(V_res[1]), 1.0, places=4)

if __name__ == "__main__":
    unittest.main()
