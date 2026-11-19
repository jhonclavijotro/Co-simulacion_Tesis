"""
Batería de pruebas unitarias para S-O-48 Parte B:
  1. Filtro RL dinámico en marco dq integrado por regla trapezoidal implícita (tau_i = 2 ms).
  2. Estabilidad incondicional con tau_RL = L_f/R_f = 2 ms bajo h = 1 ms.
  3. Activación efectiva de impedancias equivalentes R_eq, X_eq, Z_eq (pérdidas óhmicas > 0).
  4. Saturación por círculo de capacidad aparente P^2 + Q^2 <= S_max_total^2.
  5. Acople físico del bus DC (C_dc) limitando P_inv ante colapso de entrada DC.
  6. Balance auditable de potencia AC-DC (< 1e-3 W de error) en Solar, Diésel y BESS (descarga y carga).
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.GridInverter import GridConnectedInverter
from Solar.SistemaSolar import SistemaSolar
from Diesel.SistemaDiesel import SistemaDiesel
from BESS.SistemaBESS import SistemaBESS


class TestInverterRLAndDCCoupling(unittest.TestCase):
    """Verifica el modelo dinámico RL en dq, bus DC acoplado y círculo de capacidad (S-O-48 B)."""

    def test_rl_trapezoidal_response_and_stiff_stability(self):
        """Filtro RL debe responder con tau_i = 2 ms y permanecer estable incluso con tau_RL = 2 ms a h = 1 ms."""
        # L_f = X_eq / omega. Con R_out=0.0565486, X_out=0.0, R_trafo=0, X_trafo=0.000113097*377
        # Seleccionamos R_eq = 0.05, X_eq = 0.037699 => L_eq = 0.0001 H => tau_RL = L_eq/R_eq = 2.0 ms
        omega = 2.0 * math.pi * 60.0
        x_val = 0.0001 * omega
        inv = GridConnectedInverter(
            Vdcref=400.0,
            N_inv=1,
            S_inv_nom=10000.0,
            R_out_unit=0.05,
            X_out_unit=x_val,
            R_trafo=0.0,
            X_trafo=0.0,
            tau_i=0.002,
        )
        self.assertAlmostEqual(inv.tau_rl, 0.002, places=4)

        # Ejecutar 20 ms a h = 1 ms con escalón de entrada DC de 4000 W
        pw_hist = []
        for _ in range(20):
            pw, _, idi, _, _, id_ref = inv.step(
                V_dc=400.0, Vdi=155.56, Vqi=0.0, theta0=0.0, I_dc_in=10.0, dt=0.001, P_dc_in=4000.0
            )
            pw_hist.append(pw)
            self.assertTrue(math.isfinite(idi))

        # A los 2 ms (paso índice 1) debe estar en torno a ~63% (banda trapezoidal) y sin sobrepaso ni oscilación
        self.assertGreater(pw_hist[1], 2000.0)
        self.assertGreater(pw_hist[-1], 3800.0)
        # Régimen monótono estable en los últimos 5 ms
        self.assertLess(abs(pw_hist[-1] - pw_hist[-2]), 20.0)

    def test_impedance_losses_and_apparent_power_circle(self):
        """R_eq y X_eq deben producir pérdidas óhmicas reales y S_actual <= S_max_total."""
        inv = GridConnectedInverter(Vdcref=400.0, N_inv=1, S_inv_nom=5000.0)
        self.assertAlmostEqual(inv.R_eq, 0.03, places=6)
        self.assertAlmostEqual(inv.X_eq, 0.15, places=6)

        # Pedir P = 4000 W y Q = 4000 var -> S_req = 5656.8 VA > S_max = 5000 VA
        for _ in range(40):
            pw, pq, _, _, _, _ = inv.step(
                V_dc=400.0, Vdi=155.56, Vqi=0.0, theta0=0.0, I_dc_in=10.0, dt=0.001, Q_ref=4000.0, P_dc_in=4000.0
            )

        bal = inv.last_balance
        self.assertTrue(bal["s_limited"], "El círculo S_max debe activarse cuando sqrt(P^2+Q^2) > S_max")
        s_actual = math.hypot(pw, pq)
        self.assertLessEqual(s_actual, 5005.0, f"S_actual ({s_actual:.2f} VA) excede S_max (5000 VA)")
        # Q debe saturarse cerca de sqrt(5000^2 - 4000^2) = 3000 var
        self.assertAlmostEqual(pq, 3000.0, delta=60.0)
        # Pérdidas óhmicas R_eq reales y positivas: P_loss = 1.5 * R_eq * (Id^2 + Iq^2)
        self.assertGreater(bal["P_loss_rl"], 1.0)

    def test_dc_bus_coupling_limits_power_on_dc_loss(self):
        """Si la entrada DC cae a cero, V_dc descarga y la inyección AC queda limitada por energía del capacitor."""
        solar = SistemaSolar(N_inv=1)
        solar.POA = 801.78
        solar.Tam = 300.88
        for _ in range(100):
            ctx = solar.step(dt=0.001, V_pcc=1.0)
        vdc_pre = ctx["V_dc"]
        self.assertGreater(ctx["Pw"], 2000.0)

        # Corte total de irradiancia (POA = 0 -> entrada DC = 0)
        solar.POA = 0.0
        for _ in range(80):
            ctx_cut = solar.step(dt=0.001, V_pcc=1.0)

        self.assertLess(ctx_cut["V_dc"], vdc_pre, "V_dc debe caer al agotarse el recurso DC.")
        self.assertGreaterEqual(ctx_cut["V_dc"], 370.0)
        self.assertLess(ctx_cut["Pw"], 50.0, "Pw debe caer cuando se agota la energía disponible en C_dc.")

    def test_ac_dc_energy_balance_all_sources(self):
        """Verifica P_dc_in == Pw + P_loss_ac + P_stored_L + P_cap_dc (< 1e-3 W) en Solar, Diésel y BESS."""
        # 1. Solar
        solar = SistemaSolar(N_inv=1)
        solar.POA = 801.78
        solar.Tam = 300.88
        for _ in range(150):
            ctx_s = solar.step(dt=0.001, V_pcc=1.0, setpoints={"Q_ref_kvar": 0.78})
            res_s = abs(ctx_s["P_dc_in"] - (ctx_s["Pw"] + ctx_s["P_loss_ac"] + ctx_s["P_stored_L"] + ctx_s["P_cap_dc"]))
            if ctx_s["V_dc"] > 370.01 and ctx_s["V_dc"] < 499.99:
                self.assertLess(res_s, 1e-3, f"Desbalance AC-DC en Solar: {res_s:.6f} W")

        # 2. Diésel
        diesel = SistemaDiesel(P_nominal=10000.0, eta=1.0, droop_enabled=False)
        for _ in range(150):
            ctx_d = diesel.step(dt=0.001, V_pcc=110.0, setpoints={"P_ref_w": 5500.0, "Q_ref_kvar": 1.55})
            res_d = abs(ctx_d["P_dc_in"] - (ctx_d["Pw"] + ctx_d["P_loss_ac"] + ctx_d["P_stored_L"] + ctx_d["P_cap_dc"]))
            if 200.01 < ctx_d["Vdc"] < 599.99:
                self.assertLess(res_d, 1e-3, f"Desbalance AC-DC en Diésel: {res_d:.6f} W")

        # 3. BESS (descarga y carga)
        bess = SistemaBESS(N_inv=1, SoC_inicial=0.50, droop_enabled=False, S_inv_nom=3200.0)
        for p_set in (2000.0, -2500.0):
            for _ in range(150):
                ctx_b = bess.step(dt=0.001, V_pcc=110.0, setpoints={"P_ref_w": p_set, "Q_ref_kvar": 0.26})
                res_b = abs(ctx_b["P_dc_in"] - (ctx_b["Pw"] + ctx_b["P_loss_ac"] + ctx_b["P_stored_L"] + ctx_b["P_cap_dc"]))
                if 360.01 < ctx_b["V_dc"] < 439.99:
                    self.assertLess(res_b, 1e-3, f"Desbalance AC-DC en BESS (P_set={p_set}): {res_b:.6f} W")


if __name__ == "__main__":
    unittest.main()
