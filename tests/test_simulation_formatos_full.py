import unittest
import os
import sys
import csv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Scripts.run_simulation_bt_formatos import BTSimulationRunner

class TestSimulationFormatosFull(unittest.TestCase):
    """
    Prueba de integración de simulación completa con perfiles sintéticos en Baja Tensión (BT).
    Evalúa la ventana de 2 minutos (240 pasos @ 500 ms) y verifica la consistencia de los datos.
    """

    @classmethod
    def setUpClass(cls):
        cls.test_csv = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "output_data", "test_telemetry_formatos_bt.csv"))
        runner = BTSimulationRunner(output_csv=cls.test_csv)
        runner.run(max_steps=240)

        with open(cls.test_csv, "r", encoding="utf-8") as f:
            cls.rows = list(csv.DictReader(f))

    def test_row_count_and_timing(self):
        """Verifica que se generen exactamente 240 pasos para 120 segundos."""
        self.assertEqual(len(self.rows), 240)
        self.assertAlmostEqual(float(self.rows[0]["time_sec"]), 0.5)
        self.assertAlmostEqual(float(self.rows[-1]["time_sec"]), 120.0)

    def test_frequency_stability(self):
        """Verifica que la frecuencia del sistema no sature y permanezca en la banda de microrred."""
        f_vals = [float(r["f_sys_hz"]) for r in self.rows]
        self.assertGreaterEqual(min(f_vals), 58.5)
        self.assertLessEqual(max(f_vals), 61.5)
        avg_f = sum(f_vals) / len(f_vals)
        self.assertAlmostEqual(avg_f, 60.0, delta=0.5)

    def test_power_orders_of_magnitude(self):
        """Verifica que las potencias estén en la escala correcta de baja potencia (kW)."""
        p_net = [float(r["P_net_kW"]) for r in self.rows]
        self.assertGreater(min(p_net), -10.0)
        self.assertLess(max(p_net), 10.0)

    def test_reactive_consensus_convergence(self):
        """Verifica que el algoritmo FxTS converja en tiempo finito para reparto de reactiva."""
        # Al final de los 2 minutos, el error de consenso debe ser prácticamente nulo
        final_err = float(self.rows[-1]["error_Q_12"])
        self.assertLess(final_err, 0.01)

        q1 = float(self.rows[-1]["Q_ratio_1"])
        q2 = float(self.rows[-1]["Q_ratio_2"])
        q3 = float(self.rows[-1]["Q_ratio_3"])
        self.assertGreater(q1, 0.0)
        self.assertAlmostEqual(q1, q2, places=3)
        self.assertAlmostEqual(q2, q3, places=3)

    def test_voltage_limits(self):
        """Verifica que las tensiones nodales se mantengan dentro de la banda +/- 5% pu."""
        for r in self.rows:
            for i in range(1, 7):
                v_pu = float(r[f"V{i}_pu"])
                self.assertGreaterEqual(v_pu, 0.95)
                self.assertLessEqual(v_pu, 1.05)


if __name__ == "__main__":
    unittest.main()
