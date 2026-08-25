import unittest
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Central_PC.communication_emulator import CommunicationEmulator, SCENARIOS


class TestCommunicationEmulator(unittest.TestCase):
    """Tests unitarios para el módulo CommunicationEmulator."""

    def test_ideal_scenario_no_delay_no_loss(self):
        """En escenario IDEAL, no debe haber retardo ni pérdida de paquetes."""
        emu = CommunicationEmulator(scenario="IDEAL")
        injections = {"2": {"P": 10000, "Q": 2000}, "3": {"P": 5000, "Q": 1000}}

        t0 = time.perf_counter()
        delay = emu.apply_delay()
        elapsed = time.perf_counter() - t0

        filtered = emu.filter_injections(injections)

        self.assertEqual(delay, 0.0)
        self.assertLess(elapsed, 0.01)  # No debería dormir
        self.assertEqual(len(filtered), len(injections))
        self.assertEqual(set(filtered.keys()), set(injections.keys()))

    def test_packet_loss_filters_nodes(self):
        """Con drop_rate=1.0, todos los nodos deben ser descartados."""
        emu = CommunicationEmulator(
            scenario={"tau_min": 0, "tau_max": 0, "drop_rate": 1.0},
            seed=42
        )
        injections = {
            "2": {"P": 10000, "Q": 2000},
            "3": {"P": 5000, "Q": 1000},
            "4": {"P": -15000, "Q": -3000}
        }
        filtered = emu.filter_injections(injections)
        self.assertEqual(len(filtered), 0, "Con drop_rate=1.0 todos los paquetes deben ser descartados")

    def test_zero_drop_rate_preserves_all(self):
        """Con drop_rate=0.0, todos los nodos deben ser preservados."""
        emu = CommunicationEmulator(
            scenario={"tau_min": 0, "tau_max": 0, "drop_rate": 0.0},
            seed=42
        )
        injections = {"2": {"P": 10000, "Q": 2000}, "3": {"P": 5000, "Q": 1000}}
        filtered = emu.filter_injections(injections)
        self.assertEqual(len(filtered), len(injections))

    def test_partial_drop_rate_statistical(self):
        """Con drop_rate=0.5 y muchas iteraciones, ~50% de nodos deben ser descartados."""
        emu = CommunicationEmulator(
            scenario={"tau_min": 0, "tau_max": 0, "drop_rate": 0.5},
            seed=123
        )
        single_node = {"2": {"P": 10000, "Q": 2000}}
        received_count = 0
        trials = 1000

        for _ in range(trials):
            filtered = emu.filter_injections(single_node)
            received_count += len(filtered)

        effective_rate = received_count / trials
        # Debe estar entre 0.4 y 0.6 (tolerancia estadística)
        self.assertGreater(effective_rate, 0.40,
                           f"Tasa de recepción demasiado baja: {effective_rate}")
        self.assertLess(effective_rate, 0.60,
                        f"Tasa de recepción demasiado alta: {effective_rate}")

    def test_delay_within_bounds(self):
        """El retardo aplicado debe estar dentro de [tau_min, tau_max]."""
        emu = CommunicationEmulator(
            scenario={"tau_min": 0.01, "tau_max": 0.02, "drop_rate": 0.0},
            seed=42
        )
        for _ in range(5):
            t0 = time.perf_counter()
            delay = emu.apply_delay()
            elapsed = time.perf_counter() - t0

            self.assertGreaterEqual(delay, 0.01)
            self.assertLessEqual(delay, 0.02)
            self.assertGreaterEqual(elapsed, 0.009)  # Tolerancia de timer del OS

    def test_filter_returns_deep_copy(self):
        """filter_injections debe retornar una copia profunda, no una referencia."""
        emu = CommunicationEmulator(scenario="IDEAL")
        injections = {"2": {"P": 10000, "Q": 2000}}
        filtered = emu.filter_injections(injections)

        # Modificar el resultado no debe afectar el original
        filtered["2"]["P"] = 99999
        self.assertEqual(injections["2"]["P"], 10000)

    def test_predefined_scenarios_all_valid(self):
        """Todos los escenarios predefinidos deben ser instanciables."""
        for name in SCENARIOS:
            emu = CommunicationEmulator(scenario=name)
            self.assertEqual(emu.scenario, name)
            self.assertIsInstance(emu.get_scenario_description(), str)

    def test_custom_scenario(self):
        """Un escenario custom debe aceptar un diccionario de parámetros."""
        emu = CommunicationEmulator(
            scenario={"tau_min": 0.1, "tau_max": 0.2, "drop_rate": 0.15}
        )
        self.assertEqual(emu.scenario, "CUSTOM")
        self.assertEqual(emu.tau_min, 0.1)
        self.assertEqual(emu.tau_max, 0.2)
        self.assertEqual(emu.drop_rate, 0.15)

    def test_invalid_scenario_raises_error(self):
        """Un escenario no reconocido debe lanzar ValueError."""
        with self.assertRaises(ValueError):
            CommunicationEmulator(scenario="NONEXISTENT")

    def test_stats_accumulate_correctly(self):
        """Las estadísticas deben acumularse correctamente entre llamadas."""
        emu = CommunicationEmulator(scenario="IDEAL", seed=42)
        injections = {"2": {"P": 10000, "Q": 2000}, "3": {"P": 5000, "Q": 1000}}

        emu.filter_injections(injections)
        emu.filter_injections(injections)

        stats = emu.get_stats()
        self.assertEqual(stats["total_steps"], 2)
        self.assertEqual(stats["total_nodes_processed"], 4)
        self.assertEqual(stats["total_nodes_dropped"], 0)
        self.assertAlmostEqual(stats["effective_drop_rate"], 0.0)

    def test_seed_reproducibility(self):
        """La misma semilla debe producir los mismos resultados de filtrado."""
        injections = {"2": {"P": 10000, "Q": 2000}, "3": {"P": 5000, "Q": 1000},
                      "4": {"P": -15000, "Q": -3000}}

        results_a = []
        results_b = []

        for seed_val in [42, 42]:
            emu = CommunicationEmulator(
                scenario={"tau_min": 0, "tau_max": 0, "drop_rate": 0.5},
                seed=seed_val
            )
            run_results = []
            for _ in range(10):
                filtered = emu.filter_injections(injections)
                run_results.append(sorted(filtered.keys()))
            if not results_a:
                results_a = run_results
            else:
                results_b = run_results

        self.assertEqual(results_a, results_b, "Las mismas semillas deben producir resultados idénticos")


if __name__ == "__main__":
    unittest.main()
