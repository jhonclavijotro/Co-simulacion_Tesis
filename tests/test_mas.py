"""Pruebas unitarias para modulos del sistema MAS.

Ejecutar:
  python -m pytest tests/ -v
  python -m unittest discover tests/
"""

import sys
import unittest

sys.path.insert(0, ".")


class TestAgenteConsenso(unittest.TestCase):
    def test_init(self):
        from MAS.AgenteConsenso import AgenteConsenso
        a = AgenteConsenso(1, [2], 3)
        self.assertEqual(a.id, 1)
        self.assertEqual(a.vecinos, [2])
        self.assertEqual(a.n, 3)
        self.assertEqual(a.tabla, {1: 0.0})
        self.assertEqual(a.steps, {1: 0})

    def test_init_tabla(self):
        from MAS.AgenteConsenso import AgenteConsenso
        a = AgenteConsenso(1, [2], 3)
        a.init_tabla(0.8)
        self.assertAlmostEqual(a.tabla[1], 0.8)
        self.assertEqual(a.steps[1], 0)

    def test_actualizar_local(self):
        from MAS.AgenteConsenso import AgenteConsenso
        a = AgenteConsenso(1, [2], 3)
        a.actualizar_local(0.75, 10)
        self.assertAlmostEqual(a.tabla[1], 0.75)
        self.assertEqual(a.steps[1], 10)

    def test_recibir_vecino_nuevo(self):
        from MAS.AgenteConsenso import AgenteConsenso
        a = AgenteConsenso(1, [2], 3)
        a.recibir_vecino({2: 0.5}, {2: 5})
        self.assertAlmostEqual(a.tabla[2], 0.5)
        self.assertEqual(a.steps[2], 5)

    def test_recibir_vecino_stale(self):
        from MAS.AgenteConsenso import AgenteConsenso
        a = AgenteConsenso(1, [2], 3)
        a.recibir_vecino({2: 0.5}, {2: 10})
        a.recibir_vecino({2: 0.3}, {2: 5})  # step menor -> ignorar
        self.assertAlmostEqual(a.tabla[2], 0.5)
        self.assertEqual(a.steps[2], 10)

    def test_promedio_global(self):
        from MAS.AgenteConsenso import AgenteConsenso
        a = AgenteConsenso(1, [2, 3], 3)
        a.recibir_vecino({2: 1.0, 3: 0.0}, {2: 1, 3: 1})
        avg = a.promedio_global()
        self.assertAlmostEqual(avg, 1.0 / 3)

    def test_cobertura(self):
        from MAS.AgenteConsenso import AgenteConsenso
        a = AgenteConsenso(1, [2, 3], 3)
        self.assertEqual(a.cobertura, 1)
        a.recibir_vecino({2: 0.5}, {2: 1})
        self.assertEqual(a.cobertura, 2)
        a.recibir_vecino({3: 0.3}, {3: 1})
        self.assertEqual(a.cobertura, 3)


class TestBateriaSimplificada(unittest.TestCase):
    def test_init_default(self):
        from MAS.BESS_simplificado import BateriaSimplificada
        b = BateriaSimplificada()
        self.assertAlmostEqual(b.SoC, 0.5)
        self.assertEqual(b.P_ref, 0.0)
        self.assertAlmostEqual(b.V_pack, 480.0)

    def test_init_SoC_alto(self):
        from MAS.BESS_simplificado import BateriaSimplificada
        b = BateriaSimplificada(SoC_inicial=1.5)
        self.assertAlmostEqual(b.SoC, 1.0)

    def test_init_SoC_bajo(self):
        from MAS.BESS_simplificado import BateriaSimplificada
        b = BateriaSimplificada(SoC_inicial=-0.5)
        self.assertAlmostEqual(b.SoC, 0.0)

    def test_step_descarga(self):
        from MAS.BESS_simplificado import BateriaSimplificada
        b = BateriaSimplificada(V_nominal=48, capacidad_Ah=200, SoC_inicial=0.8)
        b.step(0.1, 5000)
        self.assertAlmostEqual(b.P_ref, 5000)
        self.assertLess(b.SoC, 0.8)  # debe bajar

    def test_step_carga(self):
        from MAS.BESS_simplificado import BateriaSimplificada
        b = BateriaSimplificada(V_nominal=48, capacidad_Ah=200, SoC_inicial=0.2)
        b.step(0.1, -5000)
        self.assertGreater(b.SoC, 0.2)  # debe subir

    def test_step_saturacion(self):
        from MAS.BESS_simplificado import BateriaSimplificada
        b = BateriaSimplificada(V_nominal=48, capacidad_Ah=200, SoC_inicial=1.0)
        # descarga muy grande
        b.step(10000, -100000)
        self.assertLessEqual(b.SoC, 1.0)
        self.assertGreaterEqual(b.SoC, 0.0)


class TestCoordinadorZMQ(unittest.TestCase):
    def test_config_default(self):
        from MAS.coordinador_zmq import CoordinadorZMQ
        coord = CoordinadorZMQ()
        self.assertEqual(coord.num_agentes, 3)
        self.assertEqual(coord.ids_agentes, [1, 2, 3])
        self.assertAlmostEqual(coord.SoC_avg, (0.8 + 0.5 + 0.3) / 3)


class TestGeneradorTopologia(unittest.TestCase):
    def test_radial(self):
        from CentralPC.generador_topologia import GeneradorTopologia
        g = GeneradorTopologia(N=3, M=1)
        ramas = g.generar_radial()
        self.assertEqual(len(ramas), 4)
        self.assertEqual(g.total_nodos, 5)

    def test_mallada(self):
        from CentralPC.generador_topologia import GeneradorTopologia
        g = GeneradorTopologia(N=3, M=1)
        ramas = g.generar_mallada()
        self.assertGreater(len(ramas), 0)

    def test_resumen(self):
        from CentralPC.generador_topologia import GeneradorTopologia
        g = GeneradorTopologia(N=4, M=2)
        r = g.resumen()
        self.assertEqual(r["N"], 4)
        self.assertEqual(r["M"], 2)
        self.assertEqual(r["total_nodos"], 7)


class TestClienteDinamica(unittest.TestCase):
    def test_imports(self):
        from MAS.cliente_dinamica import ClienteDinamica
        c = ClienteDinamica()
        self.assertIsNotNone(c)

    def test_sin_conexion(self):
        from MAS.cliente_dinamica import ClienteDinamica
        c = ClienteDinamica(puerto=19999, timeout=1.0)
        with self.assertRaises((ConnectionError, ConnectionRefusedError,
                                TimeoutError, OSError)):
            c.conectar()


class TestLoggerInflux(unittest.TestCase):
    def test_line_protocol(self):
        from CentralPC.logger_influx import LoggerInflux
        log = LoggerInflux()
        log.escribir("test", {"tag1": "val1"}, {"field1": 1.0})
        self.assertEqual(len(log._buf), 1)
        self.assertIn("test,tag1=val1 field1=1.0", log._buf[0])

    def test_medicion(self):
        from CentralPC.logger_influx import LoggerInflux
        log = LoggerInflux()
        log.log_medicion(1, 0.5, 1, 0.8, 5000)
        self.assertEqual(len(log._buf), 1)
        self.assertIn("medicion_agente,agente=agente_1", log._buf[0])


class TestGridInverter(unittest.TestCase):
    def test_decoupledC_sin_clamping(self):
        from common.GridInverter import GridConnectedInverter
        inv = GridConnectedInverter()
        Ud, Uq = inv.decoupledC(-100, -50, 377, 10, 5)
        self.assertAlmostEqual(Ud, -100 - (5 * 377 * 5e-3))
        self.assertAlmostEqual(Uq, -50 + (10 * 377 * 5e-3))

    def test_decoupledC_negativos(self):
        from common.GridInverter import GridConnectedInverter
        inv = GridConnectedInverter()
        Ud, Uq = inv.decoupledC(-1.0, -0.5, 377, 0.1, 0.1)
        self.assertLess(Ud, 0)
        self.assertLess(Uq, 0)


class TestRectificador(unittest.TestCase):
    def test_decoupledC(self):
        import numpy as np
        from common.Rectificador import Rectificador
        rect = Rectificador()
        Ud, Uq = rect.decoupledC(5, 3, 377, 2, 1)
        esperado_Ud = 5 - (1 * 377 * 5e-3)
        esperado_Uq = 3 + (2 * 377 * 5e-3)
        self.assertAlmostEqual(Ud, esperado_Ud)
        self.assertAlmostEqual(Uq, esperado_Uq)


if __name__ == "__main__":
    unittest.main()
