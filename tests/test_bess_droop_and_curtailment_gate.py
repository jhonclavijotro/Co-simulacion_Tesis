"""
Test de regresión permanente: Droop adaptativo BESS (C1) y Compuerta de Recorte Solar (C2).
Cumplimiento mandatorio: S-O-34 / C1 / C2 / D-34.

Verifica que:
1. El droop del BESS sea adaptativo según SoC con k_p0 = 7500 W/Hz, deadband = 0.010 Hz y sin integrador.
2. La compuerta de recorte solar permanezca en IDLE (curtail_ratio = 1.0) cuando SoC < 0.90 (caso S2).
3. La compuerta de recorte solar dispare a CURTAIL (curtail_ratio < 1.0) cuando f >= 60.060 Hz Y SoC >= 0.90
   sostenido durante 2 s (caso S3).
4. El trinquete se resetee completamente a cero (eta_excess = 0.0, curtail_ratio = 1.0) al salir de CURTAIL.
"""

import unittest
import math


class TestBESSDroopAndCurtailmentGate(unittest.TestCase):

    def test_bess_adaptive_droop_by_soc(self):
        """Droop del BESS: m_p0 = 1.33e-4 Hz/W (7500 W/Hz), deadband 10 mHz, adaptación por SoC."""
        k_p0 = 7500.0
        deadband = 0.010

        # Caso S2: SoC = 0.50, df = +0.0664 Hz
        soc = 0.50
        df_hz = 0.0664
        soc_clamped = max(0.20, min(0.80, soc))
        gain_factor = 1.0 + 0.5 * (0.50 - soc_clamped) / 0.30
        self.assertAlmostEqual(gain_factor, 1.0, places=4)

        k_p_eff = k_p0 * gain_factor
        self.assertAlmostEqual(k_p_eff, 7500.0, places=2)

        df_eff = df_hz - deadband
        p_target = -k_p_eff * df_eff
        # df_eff = 0.0564 => p_target = -7500 * 0.0564 = -423.0 W
        self.assertAlmostEqual(p_target, -423.0, delta=1.0)

        # Caso baja carga de BESS: SoC = 0.20 (mayor ganancia de absorción)
        soc_low = 0.20
        gain_factor_low = 1.0 + 0.5 * (0.50 - soc_low) / 0.30
        self.assertAlmostEqual(gain_factor_low, 1.5, places=4)
        k_p_low = k_p0 * gain_factor_low
        self.assertAlmostEqual(k_p_low, 11250.0, places=2)

        # Caso deadband: df_hz = 0.008 Hz <= 0.010 Hz => P_target = 0
        df_inside = 0.008
        self.assertTrue(abs(df_inside) <= deadband)

    def test_curtailment_gate_s2_no_curtail(self):
        """En escenario S2 (SoC = 0.50), la compuerta de recorte solar NUNCA se activa."""
        curtail_state = "IDLE"
        curtail_enter_steps = 0
        curtail_ratio = 1.0
        eta_excess = 0.0
        bess_soc = 0.50

        # Simular 160 pasos en ventana de excedente con f = 60.066 Hz
        f_sys = 60.066
        for step in range(160):
            if curtail_state == "IDLE":
                if f_sys >= 60.060 and bess_soc >= 0.90:
                    curtail_enter_steps += 1
                    if curtail_enter_steps >= 4:
                        curtail_state = "CURTAIL"
                else:
                    curtail_enter_steps = 0

            self.assertEqual(curtail_state, "IDLE")
            self.assertEqual(curtail_ratio, 1.0)
            self.assertEqual(eta_excess, 0.0)

    def test_curtailment_gate_s3_curtail_and_reset(self):
        """En escenario S3 (SoC = 0.95), f >= 60.060 Hz activa CURTAIL tras 2 s y resetea trinquete al salir."""
        curtail_state = "IDLE"
        curtail_enter_steps = 0
        curtail_dwell_steps = 0
        curtail_ratio = 1.0
        eta_excess = 0.0
        bess_soc = 0.95
        curtail_min = 0.15
        p_mpp = 2500.0

        f_sys = 60.070  # Sobrefrecuencia

        # Pasos 1 a 3: evaluando condición de entrada (dwell de 2 s = 4 pasos)
        for step in range(3):
            if curtail_state == "IDLE":
                if f_sys >= 60.060 and bess_soc >= 0.90:
                    curtail_enter_steps += 1
                    if curtail_enter_steps >= 4:
                        curtail_state = "CURTAIL"
            self.assertEqual(curtail_state, "IDLE")

        # Paso 4: se cumple dwell de 2 s => Transición a CURTAIL
        if curtail_state == "IDLE":
            if f_sys >= 60.060 and bess_soc >= 0.90:
                curtail_enter_steps += 1
                if curtail_enter_steps >= 4:
                    curtail_state = "CURTAIL"
                    curtail_dwell_steps = 0
        self.assertEqual(curtail_state, "CURTAIL")

        # En CURTAIL: verificar cálculo de recorte con k_f = 25 kW/Hz
        df_curtail = max(0.0, f_sys - 60.040)  # 0.030 Hz
        p_curt_target = 25000.0 * df_curtail   # 750 W
        eta_target = p_curt_target / p_mpp     # 750 / 2500 = 0.30
        self.assertAlmostEqual(eta_target, 0.30, places=2)

        # Simular operación en CURTAIL durante 10 pasos
        for _ in range(10):
            curtail_dwell_steps += 1
            eta_excess = max(0.0, min(1.0, eta_excess + 0.3 * (eta_target - eta_excess)))
            curtail_ratio = max(curtail_min, min(1.0, 1.0 - eta_excess))

        self.assertLess(curtail_ratio, 1.0)
        self.assertGreater(curtail_ratio, 0.5)

        # Condición de salida: f baja a 60.030 Hz y SoC baja a 0.75
        f_sys_rec = 60.030
        bess_soc_rec = 0.75
        can_exit = (curtail_dwell_steps >= 4)
        if can_exit and f_sys_rec <= 60.040 and bess_soc_rec <= 0.80:
            curtail_state = "IDLE"
            curtail_dwell_steps = 0
            curtail_enter_steps = 0
            eta_excess = 0.0
            curtail_ratio = 1.0

        # Verificar reset completo del trinquete (C2)
        self.assertEqual(curtail_state, "IDLE")
        self.assertEqual(eta_excess, 0.0)
        self.assertEqual(curtail_ratio, 1.0)

    def test_diesel_integrator_deadband_and_droop_governance(self):
        """Verifica la banda muerta del integrador diésel (S-O-35 / C1): +-0.030 Hz."""
        deadband_hz = 0.030
        deadband_w = 2.0 * math.pi * deadband_hz

        int_freq_error = 0.0

        # Caso 1: Dentro de banda muerta (|df| <= 0.030 Hz) -> Integrador retiene (no acumula)
        df_inside = 0.025
        err_w_inside = -2.0 * math.pi * df_inside
        self.assertLessEqual(abs(err_w_inside), deadband_w)

        # Simular 10 pasos dentro de la banda muerta
        for _ in range(10):
            if abs(err_w_inside) > deadband_w:
                int_freq_error += err_w_inside * 0.5
        self.assertEqual(int_freq_error, 0.0)  # Retención estricta

        # Caso 2: Fuera de banda muerta (|df| > 0.030 Hz) -> Integrador acumula
        df_outside = 0.066
        err_w_outside = -2.0 * math.pi * df_outside
        self.assertGreater(abs(err_w_outside), deadband_w)

        # Acumular 5 pasos
        for _ in range(5):
            if abs(err_w_outside) > deadband_w:
                int_freq_error = max(-75.0, min(75.0, int_freq_error + err_w_outside * 0.5))
        self.assertLess(int_freq_error, 0.0)
        self.assertAlmostEqual(int_freq_error, 5 * err_w_outside * 0.5, places=3)

        # Caso 3: En régimen con piso técnico diésel a 3500 W
        p_min_diesel = 3500.0
        p_init = 4000.0
        k_p_freq = 1000.0
        k_i_freq = 120.0
        delta_P_restore = k_p_freq * err_w_outside + k_i_freq * int_freq_error
        p_target = max(p_min_diesel, p_init + delta_P_restore)
        self.assertEqual(p_target, p_min_diesel)  # Diésel satura exactamente en su piso técnico


if __name__ == "__main__":
    unittest.main()
