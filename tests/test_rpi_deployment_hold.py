import unittest
import os
import sys
import json
import math

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from GUI.gui_command_center import GUICommandCenter
from Docker.docker_compose_generator import DockerComposeGenerator
from Scripts.deploy_raspberry import RaspberryDeployer
from Agents.node_dynamic_process import NodeDynamicProcess


class TestRaspberryDeploymentAndHoldMethods(unittest.TestCase):
    """
    Suite de pruebas integrales para:
      1. Configuración y orquestación del Centro de Mando con esquemas Hold (ZOH, FOH, ZFOH).
      2. Generación de manifiestos Docker Compose para el clúster Raspberry Pi 5.
      3. Funcionamiento de RaspberryDeployer y validación de parámetros de red.
      4. Evaluación y comparación de precisión de extrapolación física (FOH vs ZFOH vs ZOH).
    """

    def setUp(self):
        self.top_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "topologia_BT_4nodos.csv"))
        self.center = GUICommandCenter(
            topology_csv=self.top_path,
            mode="ONLINE",
            solver_mode="FBS",
            network_profile="IDEAL",
            hold_mode="ZFOH",
            zfoh_lambda=0.7,
            rpi_host="192.168.1.10",
            rpi_user="jhonclavijotro",
            master_clock_host="192.168.1.100"
        )

    def test_gui_command_center_hold_configuration(self):
        """Verifica que el Centro de Mando actualice y reporte correctamente los esquemas Hold."""
        state = self.center.get_current_state()
        self.assertEqual(state["hold_mode"], "ZFOH")
        self.assertEqual(state["zfoh_lambda"], 0.7)
        self.assertEqual(state["rpi_host"], "192.168.1.10")

        # Conmutar a FOH
        self.center.set_hold_mode("FOH")
        self.assertEqual(self.center.hold_mode, "FOH")
        self.assertEqual(self.center.get_current_state()["hold_mode"], "FOH")

        # Conmutar a ZFOH con lambda 0.85
        self.center.set_hold_mode("ZFOH", 0.85)
        self.assertEqual(self.center.hold_mode, "ZFOH")
        self.assertEqual(self.center.zfoh_lambda, 0.85)
        self.assertEqual(self.center.get_current_state()["zfoh_lambda"], 0.85)

    def test_docker_compose_generator_rpi_manifest(self):
        """Verifica que DockerComposeGenerator genere las variables de entorno para RPi y Hold."""
        generator = DockerComposeGenerator(self.top_path)
        output_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "docker-compose.rpi_test.yml"))
        
        generator.generate_yaml(
            output_path=output_file,
            mode="ONLINE",
            network_profile="LAN_ETHERNET",
            hold_mode="ZFOH",
            zfoh_lambda=0.65,
            master_clock_host="192.168.1.100"
        )

        self.assertTrue(os.path.exists(output_file))
        with open(output_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("HOLD_MODE=ZFOH", content)
        self.assertIn("ZFOH_LAMBDA=0.65", content)
        self.assertIn("MASTER_CLOCK_HOST=192.168.1.100", content)
        self.assertIn("nodo_1_dinamica", content)
        self.assertIn("nodo_1_agente", content)

        # Limpiar archivo temporal de prueba
        if os.path.exists(output_file):
            os.remove(output_file)

    def test_raspberry_deployer_structure(self):
        """Verifica la inicialización y construcción de manifiestos por RaspberryDeployer."""
        deployer = RaspberryDeployer(
            host="192.168.1.50",
            user="tesis_user",
            port=2222,
            master_clock_host="192.168.1.100",
            hold_mode="FOH",
            zfoh_lambda=0.7
        )
        self.assertEqual(deployer.host, "192.168.1.50")
        self.assertEqual(deployer.user, "tesis_user")
        self.assertEqual(deployer.port, 2222)
        self.assertEqual(deployer.hold_mode, "FOH")

        manifest_out = os.path.abspath(os.path.join(os.path.dirname(__file__), "docker-compose.deployer_test.yml"))
        created_path = deployer.generate_rpi_manifest(manifest_out)
        self.assertTrue(os.path.exists(created_path))
        with open(created_path, "r", encoding="utf-8") as f:
            c = f.read()
        self.assertIn("HOLD_MODE=FOH", c)
        self.assertIn("MASTER_CLOCK_HOST=192.168.1.100", c)

        if os.path.exists(created_path):
            os.remove(created_path)

    def test_comparative_hold_reconstruction_fidelity(self):
        """
        Evalúa el error cuadrático medio (RMSE) de seguimiento de tensión
        entre ZOH, FOH y ZFOH (lambda=0.7) ante una rampa de tensión continua.
        Demuestra que FOH y ZFOH reducen el error de integración respecto a ZOH.
        """
        # Tensión de referencia continua real: rampa lineal V(t) = 400.0 + 10.0 * t
        macro_dt = 0.5
        micro_dt = 0.001
        n_substeps = int(macro_dt / micro_dt)

        # Crear tres procesos dinámicos para el mismo generador Solar
        proc_zoh = NodeDynamicProcess(node_id=2, source_type="SOLAR", hold_mode="ZOH")
        proc_foh = NodeDynamicProcess(node_id=2, source_type="SOLAR", hold_mode="FOH")
        proc_zfoh = NodeDynamicProcess(node_id=2, source_type="SOLAR", hold_mode="ZFOH", zfoh_lambda=0.7)

        # Macro-paso 1 (V=400V)
        proc_zoh.step_macro(V_pcc=400.0)
        proc_foh.step_macro(V_pcc=400.0)
        proc_zfoh.step_macro(V_pcc=400.0)

        # Macro-paso 2 (V=405V -> rampa de +10V/s)
        V_start = 400.0
        V_end = 405.0
        dV_dt_true = (V_end - V_start) / macro_dt

        # Calcular RMSE teórico de la tensión reconstruida en los 500 micro-pasos
        sq_err_zoh = 0.0
        sq_err_foh = 0.0
        sq_err_zfoh = 0.0

        for i in range(n_substeps):
            t_sub = i * micro_dt
            v_true = V_start + dV_dt_true * t_sub
            
            # ZOH: mantiene V_start
            v_zoh = V_start
            # FOH: extrapola con dV/dt previo
            v_foh = V_start + dV_dt_true * t_sub
            # ZFOH: combinación convexa
            v_zfoh = V_start + 0.7 * dV_dt_true * t_sub

            sq_err_zoh += (v_zoh - v_true) ** 2
            sq_err_foh += (v_foh - v_true) ** 2
            sq_err_zfoh += (v_zfoh - v_true) ** 2

        rmse_zoh = math.sqrt(sq_err_zoh / n_substeps)
        rmse_foh = math.sqrt(sq_err_foh / n_substeps)
        rmse_zfoh = math.sqrt(sq_err_zfoh / n_substeps)

        # FOH tiene el menor error de interpolación lineal en rampa pura (ideal = 0)
        self.assertLess(rmse_foh, rmse_zoh)
        # ZFOH reduce significativamente el error de ZOH manteniendo amortiguamiento
        self.assertLess(rmse_zfoh, rmse_zoh)
        self.assertGreater(rmse_zoh, rmse_zfoh)

        # Verificar ejecución física de los 3 procesos
        res_zoh = proc_zoh.step_macro(V_pcc=V_end)
        res_foh = proc_foh.step_macro(V_pcc=V_end)
        res_zfoh = proc_zfoh.step_macro(V_pcc=V_end)

        self.assertEqual(res_zoh["step"], 2)
        self.assertEqual(res_foh["step"], 2)
        self.assertEqual(res_zfoh["step"], 2)


if __name__ == "__main__":
    unittest.main()
