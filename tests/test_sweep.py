import sys; sys.path.insert(0, ".")

import math
import tempfile
import os
import unittest


def _red_csv(lines):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
    f.write("\n".join(lines))
    f.close()
    return f.name


def _crear_red_2nodos():
    return _red_csv([
        "from_node,to_node,R_ohm,X_ohm,length_m",
        "0,1,0.05,0.02,100",
    ])


class TestFBSInit(unittest.TestCase):
    def test_carga_red(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep
        path = _crear_red_2nodos()
        try:
            fbs = ForwardBackwardSweep(path)
            self.assertEqual(fbs.n_nodos, 2)
            self.assertEqual(fbs.n_ramas, 1)
        finally:
            os.unlink(path)

    def test_orden_capas(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep
        path = _crear_red_2nodos()
        try:
            fbs = ForwardBackwardSweep(path)
            self.assertEqual(len(fbs.capas), 2)
            self.assertEqual(fbs.capas[0], {0})
            self.assertEqual(fbs.capas[1], {1})
        finally:
            os.unlink(path)

    def test_topologia_arbol(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep
        lines = [
            "from_node,to_node,R_ohm,X_ohm,length_m",
            "0,1,0.05,0.02,100",
            "1,2,0.04,0.015,80",
            "1,3,0.06,0.025,120",
        ]
        path = _red_csv(lines)
        try:
            fbs = ForwardBackwardSweep(path)
            self.assertEqual(fbs.n_nodos, 4)
            self.assertEqual(fbs.n_ramas, 3)
            # capas: 0, {1}, {2,3}
            self.assertIn(2, fbs.capas[2])
            self.assertIn(3, fbs.capas[2])
        finally:
            os.unlink(path)


class TestFBSResolver(unittest.TestCase):
    def test_sin_carga(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep
        path = _crear_red_2nodos()
        try:
            fbs = ForwardBackwardSweep(path)
            V, conv, it = fbs.resolver({})
            self.assertTrue(conv)
            self.assertEqual(V[0], complex(1.0, 0.0))
            self.assertAlmostEqual(V[1], complex(1.0, 0.0))
        finally:
            os.unlink(path)

    def test_carga_resistiva(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep
        path = _crear_red_2nodos()
        try:
            fbs = ForwardBackwardSweep(path)
            V, conv, it = fbs.resolver({1: (5000, 0)})
            self.assertTrue(conv)
            self.assertLess(abs(V[1]), 1.0)
            self.assertGreater(abs(V[1]), 0.9)
        finally:
            os.unlink(path)

    def test_carga_reactiva(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep
        path = _crear_red_2nodos()
        try:
            fbs = ForwardBackwardSweep(path)
            V, conv, it = fbs.resolver({1: (0, 5000)})
            self.assertTrue(conv)
            self.assertLess(abs(V[1]), 1.0)
        finally:
            os.unlink(path)

    def test_convergencia_tolerancia_estricta(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep
        path = _crear_red_2nodos()
        try:
            fbs = ForwardBackwardSweep(path)
            _, conv, it = fbs.resolver({1: (5000, 500)}, tol=1e-10)
            self.assertTrue(conv)
            self.assertGreater(it, 0)
        finally:
            os.unlink(path)

    def test_no_converge_max_iter(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep
        path = _crear_red_2nodos()
        try:
            fbs = ForwardBackwardSweep(path)
            _, conv, it = fbs.resolver({1: (1e10, 1e10)}, max_iter=5, tol=1e-12)
            self.assertFalse(conv)
            self.assertEqual(it, 5)
        finally:
            os.unlink(path)

    def test_relajacion_afecta(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep
        path = _crear_red_2nodos()
        try:
            fbs = ForwardBackwardSweep(path)
            V1, _, it1 = fbs.resolver({1: (5000, 500)}, relajacion=0.3)
            V2, _, it2 = fbs.resolver({1: (5000, 500)}, relajacion=0.9)
            self.assertNotEqual(it1, it2)
        finally:
            os.unlink(path)

    def test_nodos_multiples(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep
        lines = [
            "from_node,to_node,R_ohm,X_ohm,length_m",
            "0,1,0.05,0.02,100",
            "1,2,0.04,0.015,80",
        ]
        path = _red_csv(lines)
        try:
            fbs = ForwardBackwardSweep(path)
            V, conv, it = fbs.resolver({1: (3000, 500), 2: (2000, 300)})
            self.assertTrue(conv)
            self.assertGreater(abs(V[1]), abs(V[2]))
            self.assertGreater(abs(V[2]), 0.9)
        finally:
            os.unlink(path)


class TestFBSTensionesADict(unittest.TestCase):
    def test_formato(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep
        path = _crear_red_2nodos()
        try:
            fbs = ForwardBackwardSweep(path)
            V, _, _ = fbs.resolver({1: (5000, 0)})
            d = fbs.tensiones_a_dict(V)
            self.assertIn(0, d)
            self.assertIn(1, d)
            self.assertIn("magnitud_pu", d[0])
            self.assertIn("magnitud_V", d[0])
            self.assertIn("angulo_grados", d[0])
            self.assertIn("V_base", d[0])
            self.assertAlmostEqual(d[0]["magnitud_pu"], 1.0)
        finally:
            os.unlink(path)


class TestFBSCorrienteCarga(unittest.TestCase):
    def _make_fbs(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep as FBS
        return object.__new__(FBS)

    def test_pq(self):
        fbs = self._make_fbs()
        I = fbs._corriente_carga(complex(1, 0.5), "PQ", complex(0.95, 0))
        expected = (complex(1, 0.5) / complex(0.95, 0)).conjugate()
        self.assertAlmostEqual(abs(I - expected), 0, places=10)

    def test_z(self):
        fbs = self._make_fbs()
        V = complex(0.95, 0.1)
        I = fbs._corriente_carga(complex(1, 0.5), "Z", V)
        expected = V * complex(1, 0.5).conjugate()
        self.assertAlmostEqual(abs(I - expected), 0, places=10)

    def test_i(self):
        fbs = self._make_fbs()
        V = complex(0.95, 0.1)
        I = fbs._corriente_carga(complex(1, 0.5), "I", V)
        expected = abs(complex(1, 0.5)) * V / abs(V)
        self.assertAlmostEqual(abs(I - expected), 0, places=10)

    def test_tension_cero(self):
        fbs = self._make_fbs()
        I = fbs._corriente_carga(complex(1, 0), "PQ", complex(0, 0))
        self.assertEqual(I, complex(0, 0))

    def test_tension_cero_z(self):
        fbs = self._make_fbs()
        I = fbs._corriente_carga(complex(1, 0), "Z", complex(0, 0))
        self.assertEqual(I, complex(0, 0))


if __name__ == "__main__":
    unittest.main()
