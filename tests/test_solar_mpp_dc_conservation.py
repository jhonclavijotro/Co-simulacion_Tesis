"""
Test de regresión permanente: Cálculo de P_mpp sobre V_array real y conservación DC.
Cumplimiento mandatorio: S-O-33 Item 2 / S-O-34 / D-34 C-4.

Verifica que:
1. P_mpp coincida exactamente con V_array * I_pv (error <= 0.1 %).
2. La potencia AC inyectada Pw respete la conservación de potencia con la generación DC.
3. El recorte solar (curtail_ratio < 1.0) reduzca la potencia inyectada proporcionalmente
   al MPP disponible sin generar sobretensiones ficticias en V_dc.
"""

import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Solar.SistemaSolar import SistemaSolar


class TestSolarMPPAndDCConservation(unittest.TestCase):

    def setUp(self):
        self.solar = SistemaSolar(N_inv=1)

    def test_mpp_matches_varray_ipv(self):
        """P_mpp debe coincidir con V_array * I_pv con tolerancia menor al 0.1%."""
        # Ejecutar 500 ms (500 pasos de 1 ms) para estabilizar estado inicial
        for _ in range(500):
            ctx = self.solar.step(dt=0.001, V_pcc=1.0)

        v_array = ctx["V_array"]
        i_pv = ctx["I_pv"]
        p_dc_real = v_array * i_pv
        p_mpp = ctx["P_mpp"]

        self.assertGreater(p_mpp, 0.0, "P_mpp debe ser positiva.")
        self.assertGreater(p_dc_real, 0.0, "P_dc_real debe ser positiva.")

        rel_error = abs(p_mpp - p_dc_real) / p_mpp
        self.assertLess(
            rel_error,
            0.001,  # <= 0.1%
            f"P_mpp ({p_mpp:.2f} W) difiere de V_array*I_pv ({p_dc_real:.2f} W) por {rel_error*100:.4f}% > 0.1%"
        )

        # Verificar que NO se utiliza Vdcref (400V) para calcular P_mpp
        p_inflada_ficticia = 400.0 * i_pv
        self.assertLess(
            abs(p_mpp - p_dc_real),
            abs(p_mpp - p_inflada_ficticia) * 0.1,
            "P_mpp no debe inflarse usando Vdcref=400V en lugar de V_array."
        )

    def test_dc_ac_power_conservation_without_curtailment(self):
        """Sin recorte (curtail_ratio=1.0), Pw debe coincidir con P_mpp en régimen permanente."""
        for _ in range(1000):
            ctx = self.solar.step(dt=0.001, V_pcc=1.0)

        p_mpp = ctx["P_mpp"]
        pw = ctx["Pw"]

        rel_error = abs(pw - p_mpp) / p_mpp
        self.assertLess(
            rel_error,
            0.01,  # <= 1% en régimen
            f"Pw ({pw:.2f} W) difiere de P_mpp ({p_mpp:.2f} W) por {rel_error*100:.3f}%"
        )
        self.assertEqual(ctx["curtail_ratio"], 1.0)
        self.assertAlmostEqual(ctx["P_curtailed"], 0.0, places=2)

    def test_curtailment_proportionality_and_dc_balance(self):
        """Con recorte (curtail_ratio=0.75), Pw debe ser el 75% de P_mpp y P_curtailed el 25%."""
        for _ in range(500):
            self.solar.step(dt=0.001, V_pcc=1.0)

        # Aplicar recorte del 25% (ratio = 0.75)
        for _ in range(500):
            ctx = self.solar.step(dt=0.001, V_pcc=1.0, setpoints={"curtail_ratio": 0.75})

        p_mpp = ctx["P_mpp"]
        pw = ctx["Pw"]
        p_curt = ctx["P_curtailed"]
        p_loss = ctx["P_loss_ac"]
        p_stored = ctx["P_stored_L"]
        p_cap = ctx["P_cap_dc"]

        # Balance energético exacto: Pw + P_loss_ac + P_stored_L + P_cap_dc + P_curtailed == P_mpp
        self.assertAlmostEqual(pw + p_loss + p_stored + p_cap + p_curt, p_mpp, places=2)

        # Ratio efectivo
        ratio_efectivo = pw / p_mpp
        self.assertAlmostEqual(ratio_efectivo, 0.75, delta=0.01)

        # Tensión de bus DC dentro de rango normal [370, 430] V
        self.assertGreaterEqual(ctx["V_dc"], 370.0)
        self.assertLessEqual(ctx["V_dc"], 430.0)


if __name__ == "__main__":
    unittest.main()
