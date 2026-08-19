import os
import sys
import importlib.util

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from GUI.gui_command_center import GUICommandCenter

try:
    from scripts.deploy_raspberry import RaspberryDeployer
except ModuleNotFoundError:
    deploy_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "deploy_raspberry.py"))
    spec = importlib.util.spec_from_file_location("scripts.deploy_raspberry", deploy_path)
    deploy_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deploy_mod)
    RaspberryDeployer = deploy_mod.RaspberryDeployer

class TestEndToEndHILPlan(unittest.TestCase):

    def setUp(self):
        self.top_bt = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "topologia_BT_4nodos.csv"))
        self.test_compose = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docker-compose.hiltest.yml"))

    def tearDown(self):
        if os.path.exists(self.test_compose):
            os.remove(self.test_compose)
        import time
        time.sleep(0.1)  # Margen para que ZMQ libere puertos

    def test_p1_raspberry_script_instantiation(self):
        """Prueba 1: Verificación de configuración e instanciación del instalador RPi 5."""
        deployer = RaspberryDeployer(host="192.168.1.10", user="jhonclavijotro")
        self.assertEqual(deployer.host, "192.168.1.10")
        self.assertEqual(deployer.user, "jhonclavijotro")

    def test_p2_to_p5_gui_end_to_end_flow(self):
        """Pruebas 2 a 5: Despliegue 1-Clic, ZMQ Master, MQTT e InfluxDB Telemetría."""
        center = GUICommandCenter(topology_csv=self.top_bt, mode="ONLINE", solver_mode="FBS")
        
        # 1-Click Deployment
        out_yaml = center.deploy_containers("docker-compose.hiltest.yml")
        self.assertTrue(os.path.exists(out_yaml))

        # Co-simulation round
        try:
            history = center.run_simulation(max_steps=3, port_rep=5590, port_pub=5591)
            self.assertEqual(len(history), 3)
            self.assertIn("voltages", history[0])
        finally:
            if center.master_clock:
                try:
                    center.master_clock.close()
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
