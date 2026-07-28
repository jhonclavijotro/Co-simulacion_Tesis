import sys; sys.path.insert(0, ".")

import threading
import time
import unittest


class TestRelojZMQInit(unittest.TestCase):
    def test_init(self):
        from CentralPC.reloj_zmq import RelojZMQ
        r = RelojZMQ(puerto=5555, paso_maestro=0.05, timeout_ms=2000)
        self.assertEqual(r.puerto, 5555)
        self.assertAlmostEqual(r.paso_maestro, 0.05)
        self.assertAlmostEqual(r.timeout, 2.0)

    def test_detener_sin_iniciar(self):
        from CentralPC.reloj_zmq import RelojZMQ
        r = RelojZMQ(puerto=5556)
        r.detener()


class TestAgenteZMQInit(unittest.TestCase):
    def test_init(self):
        from MAS.agente_zmq import AgenteZMQ
        a = AgenteZMQ(id_agente=1, host="127.0.0.1", puerto=5555)
        self.assertEqual(a.id, 1)
        self.assertEqual(a.host, "127.0.0.1")
        self.assertEqual(a.puerto, 5555)
        self.assertAlmostEqual(a.timeout, 5.0)


class TestZMQIntegracion(unittest.TestCase):
    def test_handshake(self):
        from CentralPC.reloj_zmq import RelojZMQ
        from MAS.agente_zmq import AgenteZMQ

        puerto = 15551
        listo_para_tick = threading.Event()
        tick_enviado = threading.Event()

        def servidor():
            r = RelojZMQ(puerto=puerto, paso_maestro=0.05, timeout_ms=5000)
            r.iniciar()
            r.esperar_agentes(1, timeout=10.0)
            listo_para_tick.set()
            tick_enviado.wait(timeout=10)
            r.enviar_tick(1, 0.1, {"A": 1.0, "B": 0.98}, 5000)
            time.sleep(0.5)

        t = threading.Thread(target=servidor, daemon=True)
        t.start()
        time.sleep(1.0)

        a = AgenteZMQ(id_agente=42, host="127.0.0.1", puerto=puerto, timeout_ms=5000)
        a.conectar()
        listo_para_tick.wait(timeout=10)
        time.sleep(0.5)
        tick_enviado.set()

        tick = a.esperar_tick()
        a.desconectar()

        self.assertIsNotNone(tick)
        if tick is not None:
            self.assertEqual(tick["tipo"], "tick")
            self.assertEqual(tick["step"], 1)
            self.assertAlmostEqual(tick["tiempo"], 0.1)
            self.assertEqual(tick["demanda_w"], 5000)


if __name__ == "__main__":
    unittest.main()
