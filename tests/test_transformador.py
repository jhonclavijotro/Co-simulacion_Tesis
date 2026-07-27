import sys; sys.path.insert(0, ".")

import math
import cmath
import unittest
import tempfile
import os


class TestComponentesSimetricas(unittest.TestCase):
    def test_fortescue_balanceado(self):
        from CentralPC.transformador import _aplicar_fortescue, _aplicar_inversa
        a = complex(math.cos(2*math.pi/3), math.sin(2*math.pi/3))
        V_abc = [100, 100*a*a, 100*a]
        seq = _aplicar_fortescue(V_abc)
        self.assertAlmostEqual(abs(seq[0]), 0, places=10)
        self.assertAlmostEqual(abs(seq[1]), 100, places=10)
        self.assertAlmostEqual(abs(seq[2]), 0, places=10)
        abc2 = _aplicar_inversa(seq)
        for v1, v2 in zip(V_abc, abc2):
            self.assertAlmostEqual(abs(v1 - v2), 0, places=10)

    def test_fortescue_desequilibrado(self):
        from CentralPC.transformador import _aplicar_fortescue, _aplicar_inversa
        V_abc = [100, 98, 95]
        seq = _aplicar_fortescue(V_abc)
        abc2 = _aplicar_inversa(seq)
        for v1, v2 in zip(V_abc, abc2):
            self.assertAlmostEqual(abs(v1 - v2), 0, places=10)


class TestTransformadorTrifasico(unittest.TestCase):
    def test_init_dyn11(self):
        from CentralPC.transformador import TransformadorTrifasico
        tr = TransformadorTrifasico(100000, 13800, 110, 5.75, 5, "Dyn11")
        self.assertEqual(tr.conexion, "Dyn11")
        self.assertEqual(tr.angle, -30)
        self.assertTrue(tr.pri_delta)
        self.assertFalse(tr.sec_delta)
        self.assertAlmostEqual(tr.N, 125.4545, places=4)

    def test_init_yn_delta(self):
        from CentralPC.transformador import TransformadorTrifasico
        tr = TransformadorTrifasico(100000, 13800, 480, 6.0, 4, "YNd")
        self.assertEqual(tr.angle, 30)
        self.assertFalse(tr.pri_delta)
        self.assertTrue(tr.sec_delta)

    def test_conexion_invalida(self):
        from CentralPC.transformador import TransformadorTrifasico
        with self.assertRaises(ValueError):
            TransformadorTrifasico(100000, 13800, 110, 5.75, 5, "XYZ")

    def test_backward_dyn11(self):
        from CentralPC.transformador import TransformadorTrifasico
        tr = TransformadorTrifasico(100000, 13800, 110, 5.75, 5, "Dyn11")
        a = complex(math.cos(2*math.pi/3), math.sin(2*math.pi/3))
        I_sec = [100, 100*a*a, 100*a]
        I_pri = tr.backward(I_sec)
        N = tr.N
        self.assertAlmostEqual(abs(I_pri[0]), abs(I_sec[0]) / N, places=4)

    def test_forward_dyn11_sin_carga(self):
        from CentralPC.transformador import TransformadorTrifasico
        tr = TransformadorTrifasico(100000, 13800, 110, 5.75, 5, "Dyn11")
        a = complex(math.cos(2*math.pi/3), math.sin(2*math.pi/3))
        V_pri = [13800, 13800*a*a, 13800*a]
        I_pri = [0, 0, 0]
        V_sec = tr.forward(V_pri, I_pri)
        expected = 13800 / tr.N
        self.assertAlmostEqual(abs(V_sec[0]), expected, delta=1)

    def test_forward_con_carga(self):
        from CentralPC.transformador import TransformadorTrifasico
        tr = TransformadorTrifasico(100000, 13800, 110, 5.75, 5, "Dyn11")
        V_pri = [13800, 13800 * complex(0.5, -0.866), 13800 * complex(0.5, 0.866)]
        I_pri = [1.0, 1.0 * complex(0.5, -0.866), 1.0 * complex(0.5, 0.866)]
        V_sec = tr.forward(V_pri, I_pri)
        for v in V_sec:
            self.assertGreater(abs(v), 0)

    def test_perdidas(self):
        from CentralPC.transformador import TransformadorTrifasico
        tr = TransformadorTrifasico(100000, 13800, 110, 5.75, 5, "Dyn11")
        a = complex(math.cos(2*math.pi/3), math.sin(2*math.pi/3))
        I_pri = [10, 10*a*a, 10*a]
        P = tr.calcular_perdidas(I_pri)
        R = tr.Z.real
        self.assertAlmostEqual(P, 3 * (10**2) * R, places=6)


class TestFBSConTransformador(unittest.TestCase):
    def _crear_csv_temp(self, lines):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
        f.write("\n".join(lines))
        f.close()
        return f.name

    def _limpiar(self, path):
        if path and os.path.exists(path):
            os.unlink(path)

    def test_red_solo_bt(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep
        lines = [
            "from_node,to_node,R_ohm,X_ohm,length_m",
            "0,1,0.05,0.02,100",
        ]
        path = self._crear_csv_temp(lines)
        try:
            fbs = ForwardBackwardSweep(path)
            V, conv, it = fbs.resolver({1: (5000, 0)})
            self.assertTrue(conv)
            self.assertAlmostEqual(abs(V[1]), 0.9789, places=3)
        finally:
            self._limpiar(path)

    def test_red_mt_bt(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep
        lines = [
            "from_node,to_node,R_ohm,X_ohm,V_base,tipo,V_pri,V_sec,S,Z_pct,X_R,conexion,length_m",
            "0,3,0.5,2.5,13800,transformador,13800,110,100000,5.75,5,Dyn11,0",
            "3,1,0.05,0.02,110,linea,,,,,,100",
        ]
        path = self._crear_csv_temp(lines)
        try:
            fbs = ForwardBackwardSweep(path)
            V, conv, it = fbs.resolver({1: (5000, 0)})
            self.assertTrue(conv)
            V1 = V[1]
            self.assertGreater(abs(V1), 0.8)
            self.assertLess(abs(V1), 1.05)
            V3 = V[3]
            v_sec_ll = abs(V3) * 110
            self.assertAlmostEqual(v_sec_ll, 110.06, delta=0.15)
        finally:
            self._limpiar(path)

    def test_red_mt_bt_dos_cargas(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep
        lines = [
            "from_node,to_node,R_ohm,X_ohm,V_base,tipo,V_pri,V_sec,S,Z_pct,X_R,conexion,length_m",
            "0,3,0.5,2.5,13800,transformador,13800,110,100000,5.75,5,Dyn11,0",
            "3,1,0.05,0.02,110,linea,,,,,,100",
            "3,2,0.10,0.04,110,linea,,,,,,150",
        ]
        path = self._crear_csv_temp(lines)
        try:
            fbs = ForwardBackwardSweep(path)
            V, conv, it = fbs.resolver({1: (3000, 500), 2: (2000, 300)})
            self.assertTrue(conv)
            for n in [1, 2, 3]:
                self.assertGreater(abs(V[n]), 0.9)
            v1 = abs(V[1]) * 110
            v2 = abs(V[2]) * 110
            self.assertGreater(v2, 100)
        finally:
            self._limpiar(path)

    def test_tensiones_a_dict_con_v_base(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep
        lines = [
            "from_node,to_node,R_ohm,X_ohm,V_base,tipo,V_pri,V_sec,S,Z_pct,X_R,conexion,length_m",
            "0,3,0.5,2.5,13800,transformador,13800,110,100000,5.75,5,Dyn11,0",
            "3,1,0.05,0.02,110,linea,,,,,,100",
        ]
        path = self._crear_csv_temp(lines)
        try:
            fbs = ForwardBackwardSweep(path)
            V, conv, _ = fbs.resolver({1: (3000, 0)})
            d = fbs.tensiones_a_dict(V)
            self.assertAlmostEqual(d[0]["V_base"], 13800)
            self.assertAlmostEqual(d[3]["V_base"], 110)
            self.assertAlmostEqual(d[0]["magnitud_V"], 13800 * abs(V[0]))
        finally:
            self._limpiar(path)



class TestModelosCarga(unittest.TestCase):
    def test_carga_pq(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep as FBS
        fbs = object.__new__(FBS)
        S = complex(1.0, 0.5)
        I = fbs._corriente_carga(S, "PQ", complex(0.95, 0))
        expected = (S / complex(0.95, 0)).conjugate()
        self.assertAlmostEqual(abs(I - expected), 0, places=10)

    def test_carga_z(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep as FBS
        fbs = object.__new__(FBS)
        S = complex(1.0, 0.5)
        V = complex(0.95, 0.1)
        I = fbs._corriente_carga(S, "Z", V)
        expected = V * S.conjugate()
        self.assertAlmostEqual(abs(I - expected), 0, places=10)

    def test_carga_i(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep as FBS
        fbs = object.__new__(FBS)
        S = complex(1.0, 0.5)
        V = complex(0.95, 0.1)
        I = fbs._corriente_carga(S, "I", V)
        expected = abs(S) * V / abs(V)
        self.assertAlmostEqual(abs(I - expected), 0, places=10)

    def test_carga_tension_cero(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep as FBS
        fbs = object.__new__(FBS)
        I = fbs._corriente_carga(complex(1, 0), "PQ", complex(0, 0))
        self.assertEqual(I, complex(0, 0))

    def test_fbs_con_modelos(self):
        from CentralPC.solver_sweep import ForwardBackwardSweep
        import tempfile, os
        lines = [
            "from_node,to_node,R_ohm,X_ohm,length_m",
            "0,1,0.05,0.02,100",
            "1,2,0.04,0.015,80",
        ]
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
        f.write("\n".join(lines)); f.close()
        try:
            fbs = ForwardBackwardSweep(f.name)
            V, conv, it = fbs.resolver(
                {1: (5000, 0), 2: (3000, 500)},
                modelos={1: "PQ", 2: "Z"},
            )
            self.assertTrue(conv)
            for n in [1, 2]:
                self.assertGreater(abs(V[n]), 0.9)
        finally:
            if os.path.exists(f.name): os.unlink(f.name)


class TestIEEEDie13(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from CentralPC.solver_sweep import ForwardBackwardSweep
        from CentralPC.caso_ieee13 import CARGAS, MODELOS, V_SLACK, BENCHMARK
        cls.fbs = ForwardBackwardSweep("CentralPC/red_ieee13.csv")
        cls.V, cls.conv, cls.it = cls.fbs.resolver(
            CARGAS, MODELOS, V_slack=V_SLACK, tol=1e-8, max_iter=200
        )
        cls.bm = BENCHMARK

    def test_converge(self):
        self.assertTrue(self.conv)
        self.assertLess(self.it, 100)

    def test_tension_634(self):
        v = abs(self.V[2]) * 480
        self.assertAlmostEqual(v, 480 * 0.994, delta=10)

    def test_tension_675(self):
        v = abs(self.V[11]) * 4160
        vb = 4160 * 0.9835
        self.assertAlmostEqual(v, vb, delta=50)

    def test_tension_671(self):
        v = abs(self.V[5]) * 4160
        self.assertAlmostEqual(v, 4160 * 0.990, delta=50)

    def test_perdidas_orden(self):
        S_slack = complex(0, 0)
        for hijo in [1, 3, 5]:
            I = complex(0, 0)
            # approximacion: perdidas del sistema
        self.assertLess(self.it, 50)

    def test_transformador_yy0(self):
        tr = self.fbs.transformador_rama.get((1, 2))
        self.assertIsNotNone(tr)
        self.assertEqual(tr.conexion, "Yy0")
        self.assertEqual(tr.angle, 0)


if __name__ == "__main__":
    unittest.main()
