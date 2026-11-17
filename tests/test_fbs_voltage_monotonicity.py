"""
Test de regresión permanente: Monotonía del perfil de tensión bajo carga pura en FBS.
Cumplimiento mandatorio: S-O-34 / C0 / D-34.

Verifica que en la red del banco de 8 nodos bajo carga pura (inyecciones netas negativas P < 0, Q < 0)
y sin generación distribuida, la magnitud de tensión |V| decrezca monótonamente a lo largo
de las ramas y de cada camino radial desde el nodo raíz/slack (N1 = 1.0 pu) hasta las hojas:
  - Camino 1: N1 -> N2 -> N4 (|V1| > |V2| > |V4|)
  - Camino 2: N1 -> N2 -> N5 (|V1| > |V2| > |V5|)
  - Camino 3: N1 -> N3 -> N6 (|V1| > |V3| > |V6|)
  - Camino 4: N1 -> N3 -> N7 -> N8 (|V1| > |V3| > |V7| > |V8|)
"""

import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Central_PC.power_flow_fbs import ForwardBackwardSweepSolver


class TestFBSVoltageMonotonicity(unittest.TestCase):

    def setUp(self):
        self.top_8nodos = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "Forms", "ensayos_red_hil", "topologia_red_8nodos.csv")
        )
        self.solver = ForwardBackwardSweepSolver(V_base=400.0, S_base=10000.0)
        self.solver.load_topology(self.top_8nodos)

    def test_pure_load_monotonicity_8nodes(self):
        """Bajo carga pura en N4-N8, |V| debe decrecer monótonamente a lo largo de cada rama y camino radial."""
        # Cargas residenciales representativas (consumo: inyecciones negativas)
        P_injections = {4: -600.0, 5: -800.0, 6: -500.0, 7: -400.0, 8: -700.0}
        Q_injections = {4: -120.0, 5: -160.0, 6: -100.0, 7: -80.0, 8: -140.0}

        V, converged, iters = self.solver.solve(P_injections, Q_injections)
        self.assertTrue(converged, "El flujo FBS debe converger bajo carga pura.")
        self.assertLessEqual(iters, 20)

        # Slack fijo en 1.0 pu
        self.assertAlmostEqual(abs(V[1]), 1.0, places=5)

        # 1. Verificar caída física monótona en cada rama individual (from -> to): |V_from| > |V_to|
        for br in self.solver.branches:
            u, v = br["from"], br["to"]
            v_u = abs(V[u])
            v_v = abs(V[v])
            self.assertGreater(
                v_u,
                v_v,
                f"Violación de caída física en rama ({u} -> {v}): |V_{u}|={v_u:.6f} pu <= |V_{v}|={v_v:.6f} pu"
            )

        # 2. Verificar monotonía estricta a lo largo de cada camino radial raíz -> hoja:
        radial_paths = [
            [1, 2, 4],       # Camino al alimentador N4
            [1, 2, 5],       # Camino al alimentador N5
            [1, 3, 6],       # Camino al alimentador N6
            [1, 3, 7, 8],    # Camino largo N7-N8
        ]

        for path in radial_paths:
            path_str = " -> ".join(f"N{n}" for n in path)
            for i in range(len(path) - 1):
                u, v = path[i], path[i + 1]
                self.assertGreater(
                    abs(V[u]),
                    abs(V[v]),
                    f"Violación de monotonía en camino {path_str}: |V_{u}|={abs(V[u]):.6f} <= |V_{v}|={abs(V[v]):.6f}"
                )

        # 3. Ningún nodo de carga puede tener tensión superior al slack
        for n in range(2, 9):
            self.assertLess(
                abs(V[n]),
                1.0,
                f"Nodo {n} tiene tensión |V|={abs(V[n]):.6f} >= 1.0 pu bajo carga pura."
            )

    def test_pure_generation_voltage_rise_8nodes(self):
        """Con inyección de generación positiva neta en N2 o N3, la tensión local debe elevarse."""
        # Solo inyección solar masiva en N2 (3000 W) sin cargas
        P_injections = {2: 3000.0}
        Q_injections = {2: 0.0}

        V, converged, iters = self.solver.solve(P_injections, Q_injections)
        self.assertTrue(converged)
        # La inyección en N2 debe elevar la tensión sobre el slack aguas abajo
        self.assertGreater(abs(V[2]), 1.0)


if __name__ == "__main__":
    unittest.main()
