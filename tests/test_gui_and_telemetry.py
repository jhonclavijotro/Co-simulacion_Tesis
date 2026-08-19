import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from GUI.mqtt_publisher import MQTTPublisher
from GUI.influx_telemetry import InfluxTelemetryLogger
from GUI.gui_command_center import GUICommandCenter

class TestGUIAndTelemetry(unittest.TestCase):

    def setUp(self):
        self.top_bt = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "topologia_BT_4nodos.csv"))
        self.test_compose = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docker-compose.guitest.yml"))

    def tearDown(self):
        if os.path.exists(self.test_compose):
            os.remove(self.test_compose)
        import time
        time.sleep(0.1)  # Permite que ZMQ libere los descriptores de red

    def test_mqtt_publisher_payloads(self):
        pub = MQTTPublisher()
        payloads = pub.publish_step(5)
        self.assertIn("microgrid/meteorologia/solar", payloads)
        self.assertIn("microgrid/meteorologia/eolica", payloads)
        self.assertIn("microgrid/meteorologia/hidrica", payloads)
        self.assertIn("POA", payloads["microgrid/meteorologia/solar"])

    def test_influx_telemetry_logging(self):
        logger = InfluxTelemetryLogger()
        voltages = {1: {"V_pu": 1.0, "V_volts": 400.0}}
        powers = {1: {"P": 5000.0, "Q": 1000.0}}
        rec = logger.log_step(1, "ONLINE", voltages, powers)
        logger.close()

        self.assertEqual(rec["step"], 1)
        self.assertEqual(rec["mode"], "ONLINE")

    def test_gui_command_center_flow(self):
        center = GUICommandCenter(topology_csv=self.top_bt, mode="ONLINE", solver_mode="FBS")
        out_yaml = center.deploy_containers(self.test_compose)
        self.assertTrue(os.path.exists(out_yaml))

        try:
            history = center.run_simulation(max_steps=2, port_rep=5565, port_pub=5566)
            self.assertEqual(len(history), 2)
        finally:
            if center.master_clock:
                try:
                    center.master_clock.close()
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
