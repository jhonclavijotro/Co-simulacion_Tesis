import unittest
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Central_PC.master_clock_zmq import MasterClockZMQ


class TestMasterClockZMQ(unittest.TestCase):

    def setUp(self):
        self.top_bt = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "topologia_BT_4nodos.csv"))
        self._masters = []

    def _make_master(self, mode, port_rep, port_pub, **kwargs):
        """Crea un MasterClockZMQ y lo registra para limpieza automática en tearDown."""
        master = MasterClockZMQ(self.top_bt, mode=mode, port_rep=port_rep, port_pub=port_pub, **kwargs)
        self._masters.append(master)
        return master

    def tearDown(self):
        """Cierra todos los sockets ZMQ y espera para garantizar la liberación de puertos."""
        for m in self._masters:
            try:
                m.close()
            except Exception:
                pass
        self._masters.clear()
        time.sleep(0.1)  # Margen para que ZMQ libere los descriptores de red

    def test_master_step_fbs(self):
        master = self._make_master("FBS", port_rep=5557, port_pub=5558)
        injections = {
            "2": {"P": 8000.0, "Q": 1500.0},
            "4": {"P": -12000.0, "Q": -2500.0}
        }
        res = master.run_step(injections)
        self.assertEqual(res["step"], 1)
        self.assertEqual(res["mode"], "FBS")
        self.assertTrue(res["converged"])
        self.assertIn(1, res["voltages"])
        self.assertIn(4, res["voltages"])

    def test_master_step_sensitivity(self):
        master = self._make_master("SENSITIVITY", port_rep=5559, port_pub=5560)
        injections = {
            "2": {"P": 8000.0, "Q": 1500.0},
            "4": {"P": -12000.0, "Q": -2500.0}
        }
        res = master.run_step(injections)
        self.assertEqual(res["step"], 1)
        self.assertEqual(res["mode"], "SENSITIVITY")
        self.assertTrue(res["converged"])
    def test_hold_last_value_and_breaker_trip(self):
        # max_hold_seconds = 1.0s -> 2 steps at dt=0.5s
        master = self._make_master("FBS", port_rep=5561, port_pub=5562, max_hold_seconds=1.0)
        
        # Paso 1: Nodo 2 inyecta 10 kW
        inj1 = {"2": {"P": 10000.0, "Q": 1000.0}}
        res1 = master.run_step(inj1)
        self.assertNotIn(2, res1["stale_nodes"])
        self.assertNotIn(2, res1["tripped_nodes"])
        self.assertEqual(master.last_known_injections[2]["P"], 10000.0)

        # Paso 2: Paquete se pierde (0.5s sin recibir) -> Hold Last Value
        res2 = master.run_step({})
        self.assertIn(2, res2["stale_nodes"])
        self.assertNotIn(2, res2["tripped_nodes"])

        # Paso 3: Sigue sin recibir (1.0s sin recibir) -> Hold Last Value
        res3 = master.run_step({})
        self.assertIn(2, res3["stale_nodes"])
        self.assertNotIn(2, res3["tripped_nodes"])

        # Paso 4: Supera 1.0s (1.5s sin recibir) -> Disyuntor trip (P=0, Q=0)
        res4 = master.run_step({})
        self.assertIn(2, res4["tripped_nodes"])

    def test_operating_mode_transition(self):
        master = self._make_master("FBS", port_rep=5563, port_pub=5564)
        mode, slack, v_ref = master.set_operating_mode("OFFLINE", slack_node=1, V_slack=1.02)
        self.assertEqual(mode, "OFFLINE")
        self.assertEqual(slack, 1)
        self.assertEqual(v_ref, 1.02)


if __name__ == "__main__":
    unittest.main()
