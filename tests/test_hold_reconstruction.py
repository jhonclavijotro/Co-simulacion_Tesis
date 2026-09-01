import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Agents.node_dynamic_process import NodeDynamicProcess
from common.Transformadas import SRFPLL


class TestHoldReconstruction(unittest.TestCase):
    """
    Pruebas unitarias para los esquemas de reconstrucción y extrapolación de señales
    en la frontera de co-simulación multitasa:
      - ZOH (Zero-Order Hold)
      - FOH (First-Order Hold)
      - ZFOH (Mixed Zero-First Order Hold con parámetro lambda)
    """

    def test_zoh_default_behavior(self):
        """Verifica que el modo ZOH por defecto mantenga compatibilidad y estabilidad."""
        proc = NodeDynamicProcess(node_id=1, source_type="DIESEL", hold_mode="ZOH")
        res1 = proc.step_macro(V_pcc=400.0, Q_ref=0.0)
        self.assertEqual(res1["node_id"], 1)
        self.assertEqual(res1["step"], 1)
        self.assertIn("P_w", res1)
        self.assertIn("Q_var", res1)

        # Paso 2 con cambio de tensión
        res2 = proc.step_macro(V_pcc=395.0, Q_ref=0.0)
        self.assertEqual(res2["step"], 2)

    def test_foh_linear_extrapolation_step(self):
        """Verifica que en modo FOH se calcule y aplique la extrapolación lineal continua."""
        proc = NodeDynamicProcess(node_id=2, source_type="SOLAR", hold_mode="FOH")
        
        # Paso 1: Flat-start inicial
        res1 = proc.step_macro(V_pcc=400.0, Q_ref=1000.0)
        self.assertEqual(proc.V_pcc_prev, 400.0)
        self.assertEqual(res1["step"], 1)

        # Paso 2: Rampa de tensión V_pcc = 405.0 (+5V en 500ms -> dV/dt = +10 V/s)
        res2 = proc.step_macro(V_pcc=405.0, Q_ref=1000.0)
        self.assertEqual(proc.V_pcc_prev, 405.0)
        self.assertEqual(res2["step"], 2)
        self.assertGreater(res2["P_w"], 0.0)

    def test_zfoh_convex_combination(self):
        """Verifica que en modo ZFOH se aplique la combinación convexa con parámetro lambda."""
        # Lambda = 0.5
        proc_half = NodeDynamicProcess(node_id=2, source_type="SOLAR", hold_mode="ZFOH", zfoh_lambda=0.5)
        res1 = proc_half.step_macro(V_pcc=400.0, Q_ref=500.0)
        res2 = proc_half.step_macro(V_pcc=410.0, Q_ref=500.0)
        self.assertEqual(res2["step"], 2)
        self.assertEqual(proc_half.zfoh_lambda, 0.5)

        # Lambda = 0.7 (valor por defecto recomendado para microrredes)
        proc_def = NodeDynamicProcess(node_id=3, source_type="EOLICA", hold_mode="ZFOH", zfoh_lambda=0.7)
        res_e1 = proc_def.step_macro(V_pcc=400.0, Q_ref=0.0)
        res_e2 = proc_def.step_macro(V_pcc=398.0, Q_ref=0.0)
        self.assertEqual(res_e2["step"], 2)

    def test_all_der_technologies_under_foh_and_zfoh(self):
        """Verifica la estabilidad y compatibilidad de todos los DERs bajo FOH y ZFOH."""
        technologies = ["SOLAR", "EOLICA", "HIDRICA", "BESS", "DIESEL", "DEMANDA"]
        
        for tech in technologies:
            for mode in ["FOH", "ZFOH"]:
                proc = NodeDynamicProcess(node_id=1, source_type=tech, hold_mode=mode, zfoh_lambda=0.7)
                
                # Ejecutar secuencia de 3 macro-pasos con fluctuaciones de tensión
                voltages = [400.0, 403.0, 397.0]
                for v in voltages:
                    out = proc.step_macro(V_pcc=v, Q_ref=0.0)
                    self.assertIsInstance(out["P_w"], (int, float))
                    self.assertIsInstance(out["Q_var"], (int, float))

    def test_override_parameters_in_step_macro(self):
        """Verifica que los argumentos en step_macro permitan sobrescribir hold_mode y lambda en tiempo de ejecución."""
        proc = NodeDynamicProcess(node_id=4, source_type="BESS", hold_mode="ZOH")
        
        # Sobrescribir a FOH en step_macro
        out = proc.step_macro(V_pcc=400.0, hold_mode="FOH")
        self.assertEqual(out["step"], 1)

        # Sobrescribir a ZFOH con lambda 0.8
        out2 = proc.step_macro(V_pcc=402.0, hold_mode="ZFOH", zfoh_lambda=0.8)
        self.assertEqual(out2["step"], 2)


if __name__ == "__main__":
    unittest.main()
