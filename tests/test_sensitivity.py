import sys; sys.path.insert(0, ".")

import tempfile
import os
import unittest

from CentralPC.solver_sensitivity import SensitivitySolver


def _red_csv(lines):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
    f.write("\n".join(lines))
    f.close()
    return f.name


class TestSensitivityInit(unittest.TestCase):
    def test_init(self):
        path = _red_csv([
            "from_node,to_node,R_ohm,X_ohm,length_m",
            "0,1,0.05,0.02,100",
        ])
        try:
            ss = SensitivitySolver(path)
            self.assertIsNotNone(ss)
            self.assertFalse(ss._calibrado)
        finally:
            os.unlink(path)

    def test_str_sin_calibrar(self):
        path = _red_csv([
            "from_node,to_node,R_ohm,X_ohm,length_m",
            "0,1,0.05,0.02,100",
        ])
        try:
            ss = SensitivitySolver(path)
            s = str(ss)
            self.assertIn("sin calibrar", s)
        finally:
            os.unlink(path)


class TestSensitivityCalibrar(unittest.TestCase):
    def test_calibra_simple(self):
        path = _red_csv([
            "from_node,to_node,R_ohm,X_ohm,length_m",
            "0,1,0.05,0.02,100",
        ])
        try:
            ss = SensitivitySolver(path)
            ss.calibrar({1: (5000, 0)})
            self.assertTrue(ss._calibrado)
            self.assertIsNotNone(ss.S_VP)
            self.assertIsNotNone(ss.S_VQ)
            self.assertEqual(len(ss.S_VP), 2)
            self.assertEqual(len(ss.S_VQ), 2)
        finally:
            os.unlink(path)

    def test_str_calibrado(self):
        path = _red_csv([
            "from_node,to_node,R_ohm,X_ohm,length_m",
            "0,1,0.05,0.02,100",
        ])
        try:
            ss = SensitivitySolver(path)
            ss.calibrar({1: (5000, 0)})
            s = str(ss)
            self.assertIn("calibrado", s)
        finally:
            os.unlink(path)


class TestSensitivityPredecir(unittest.TestCase):
    def test_predice_sin_carga(self):
        path = _red_csv([
            "from_node,to_node,R_ohm,X_ohm,length_m",
            "0,1,0.05,0.02,100",
        ])
        try:
            ss = SensitivitySolver(path)
            ss.calibrar({1: (0, 0)})
            V = ss.predecir_V({0: (0, 0), 1: (0, 0)})
            self.assertAlmostEqual(V[0], 1.0, places=4)
            self.assertAlmostEqual(V[1], 1.0, places=4)
        finally:
            os.unlink(path)

    def test_predice_carga(self):
        path = _red_csv([
            "from_node,to_node,R_ohm,X_ohm,length_m",
            "0,1,0.05,0.02,100",
        ])
        try:
            ss = SensitivitySolver(path)
            ss.calibrar({1: (0, 0)})
            V = ss.predecir_V({1: (5000, 0)})
            self.assertLess(V[1], 1.0)
        finally:
            os.unlink(path)

    def test_predice_multiples_cargas(self):
        lines = [
            "from_node,to_node,R_ohm,X_ohm,length_m",
            "0,1,0.05,0.02,100",
            "1,2,0.04,0.015,80",
        ]
        path = _red_csv(lines)
        try:
            ss = SensitivitySolver(path)
            ss.calibrar({1: (0, 0), 2: (0, 0)})
            V = ss.predecir_V({1: (3000, 500), 2: (2000, 300)})
            self.assertLess(V[1], 1.0)
            self.assertLess(V[2], V[1])
        finally:
            os.unlink(path)

    def test_no_calibrado(self):
        path = _red_csv([
            "from_node,to_node,R_ohm,X_ohm,length_m",
            "0,1,0.05,0.02,100",
        ])
        try:
            ss = SensitivitySolver(path)
            with self.assertRaises(RuntimeError):
                ss.predecir_V({0: (0, 0), 1: (0, 0)})
        finally:
            os.unlink(path)


class TestSensitivityResolver(unittest.TestCase):
    def test_delega_sin_calibrar(self):
        path = _red_csv([
            "from_node,to_node,R_ohm,X_ohm,length_m",
            "0,1,0.05,0.02,100",
        ])
        try:
            ss = SensitivitySolver(path)
            V, conv, it = ss.resolver({1: (5000, 0)})
            self.assertTrue(conv)
            self.assertLess(abs(V[1]), 1.0)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
