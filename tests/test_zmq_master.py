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
        self.assertIn(1, res["voltages"])


if __name__ == "__main__":
    unittest.main()
