import unittest
import math
from common.GridInverter import GridConnectedInverter
from Solar.SistemaSolar import SistemaSolar
from BESS.SistemaBESS import SistemaBESS

class TestInverterAggregation(unittest.TestCase):
    """Pruebas unitarias para la agregacion de N_inv inversores en paralelo

    y escalado de impedancia equivalente vista desde el punto de acoplamiento.
    """

    def test_grid_inverter_impedance_and_capacity_scaling(self):
        """Verifica que S_max_total escale linealmente y Z_eq refleje el paralelismo."""
        inv_unit = GridConnectedInverter(Vdcref=400.0, N_inv=1, S_inv_nom=100000.0,
                                         R_out_unit=0.02, X_out_unit=0.10, R_trafo=0.01, X_trafo=0.05)
        
        self.assertEqual(inv_unit.S_max_total, 100000.0)
        self.assertAlmostEqual(inv_unit.R_eq, 0.03) # 0.02/1 + 0.01
        self.assertAlmostEqual(inv_unit.X_eq, 0.15) # 0.10/1 + 0.05
        
        # Planta con 10 inversores en paralelo
        inv_plant = GridConnectedInverter(Vdcref=400.0, N_inv=10, S_inv_nom=100000.0,
                                          R_out_unit=0.02, X_out_unit=0.10, R_trafo=0.01, X_trafo=0.05)
        
        self.assertEqual(inv_plant.S_max_total, 1000000.0) # 10 * 100 kVA = 1 MVA
        self.assertAlmostEqual(inv_plant.R_eq, 0.012)     # 0.02/10 + 0.01
        self.assertAlmostEqual(inv_plant.Z_eq.real, 0.012)
        self.assertAlmostEqual(inv_plant.Z_eq.imag, 0.06)

    def test_grid_inverter_power_step_scaling(self):
        """Verifica que la inyeccion de corriente y potencia activa/reactiva escale por N_inv."""
        inv_unit = GridConnectedInverter(Vdcref=400.0, N_inv=1)
        inv_plant = GridConnectedInverter(Vdcref=400.0, N_inv=5)
        
        Pw_u, Pq_u, Idi_u, Iqi_u, _, _ = inv_unit.step(V_dc=390.0, Vdi=110.0, Vqi=0.0, theta0=0.0, I_dc_in=10.0, dt=0.001)
        Pw_p, Pq_p, Idi_p, Iqi_p, _, _ = inv_plant.step(V_dc=390.0, Vdi=110.0, Vqi=0.0, theta0=0.0, I_dc_in=10.0, dt=0.001)
        
        self.assertAlmostEqual(Pw_p, Pw_u * 5)
        self.assertAlmostEqual(Idi_p, Idi_u * 5)

    def test_sistema_solar_parallel_aggregation(self):
        """Verifica que SistemaSolar soporte N_inv y mantenga coherencia en el contexto."""
        solar_single = SistemaSolar(N_inv=1)
        solar_farm = SistemaSolar(N_inv=12, V_base_MT=13800.0, S_base_planta=1200000.0)
        
        self.assertEqual(solar_single.contexto["N_inv"], 1)
        self.assertEqual(solar_farm.contexto["N_inv"], 12)
        self.assertAlmostEqual(solar_farm.contexto["I_pv"], 7.6 * 12)
        
        ctx_farm = solar_farm.step(dt=0.001)
        self.assertIn("Pw", ctx_farm)
        self.assertGreater(ctx_farm["Pw"], 0.0)

    def test_sistema_bess_parallel_aggregation(self):
        """Verifica que SistemaBESS escale la corriente maxima del inversor y capacidad con N_inv."""
        bess_single = SistemaBESS(N_inv=1, I_inv_max=50.0)
        bess_plant = SistemaBESS(N_inv=8, I_inv_max=50.0)
        
        self.assertEqual(bess_single._I_inv_max, 50.0)
        self.assertEqual(bess_plant._I_inv_max, 400.0) # 8 * 50.0 A

if __name__ == "__main__":
    unittest.main()
