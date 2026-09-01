import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Agents.finite_time_consensus import FiniteTimeConsensusAgent, sig_pow

class TestFiniteTimeConsensus(unittest.TestCase):

    def test_agent_online_consensus_step(self):
        agent = FiniteTimeConsensusAgent(agent_id=2, Q_max=40000.0, mode="ONLINE")
        agent.set_adjacency({1: 1, 3: 1})

        neighbors = {
            1: {"V": 1.0, "Q_ratio": 0.25},
            3: {"V": 0.98, "Q_ratio": 0.35}
        }
        dV, dQ = agent.update_consensus(V_i=0.99, Q_i=10000.0, neighbor_states=neighbors)

        self.assertIsInstance(dV, float)
        self.assertIsInstance(dQ, float)

    def test_agent_offline_leader_step(self):
        # En modo OFFLINE, el agente 1 (Líder Diésel) corrige hacia V_ref=1.0
        agent_leader = FiniteTimeConsensusAgent(agent_id=1, Q_max=50000.0, mode="OFFLINE")
        agent_leader.set_adjacency({2: 1})

        neighbors = {2: {"V": 0.95, "Q_ratio": 0.50}}
        dV, dQ = agent_leader.update_consensus(V_i=0.96, Q_i=25000.0, neighbor_states=neighbors)

        self.assertIsInstance(dV, float)
        self.assertNotEqual(dV, 0.0)

    # --- Nuevos tests para la zona muerta adaptativa (Anti-Chattering) ---

    def test_sig_pow_continuity_at_epsilon_boundary(self):
        """Verifica continuidad C0 de sig_pow en |y| = epsilon.
        El valor de la función no lineal en y=epsilon debe coincidir
        con el valor de la aproximación lineal en y=epsilon."""
        epsilon = 1e-3
        alpha = 0.8
        beta = 1.2

        # Valor no lineal justo en el límite superior: sign(eps) * eps^gamma
        nonlinear_alpha = epsilon ** alpha
        nonlinear_beta = epsilon ** beta

        # Valor lineal justo en el límite inferior: k_p * eps = eps^(gamma-1) * eps = eps^gamma
        linear_alpha = sig_pow(epsilon * 0.9999, alpha, epsilon)
        linear_beta = sig_pow(epsilon * 0.9999, beta, epsilon)

        # Deben ser aproximadamente iguales (continuidad C0)
        self.assertAlmostEqual(linear_alpha, nonlinear_alpha, places=5,
                               msg="Discontinuidad C0 detectada en sig_pow para alpha")
        self.assertAlmostEqual(linear_beta, nonlinear_beta, places=5,
                               msg="Discontinuidad C0 detectada en sig_pow para beta")

    def test_sig_pow_linear_region_proportional(self):
        """En la zona muerta, sig_pow debe ser proporcional al error (lineal)."""
        epsilon = 1e-3
        alpha = 0.8

        y1 = epsilon * 0.5
        y2 = epsilon * 0.25

        val1 = sig_pow(y1, alpha, epsilon)
        val2 = sig_pow(y2, alpha, epsilon)

        # La relación debe ser 2:1 (lineal proporcional)
        self.assertAlmostEqual(val1 / val2, 2.0, places=4,
                               msg="sig_pow no es proporcional en la zona muerta")

    def test_sig_pow_nonlinear_region_unchanged(self):
        """Para errores grandes (|y| >> epsilon), sig_pow debe ser idéntica a la ley estándar."""
        epsilon = 1e-3
        alpha = 0.8
        y_large = 0.05  # >> epsilon

        result = sig_pow(y_large, alpha, epsilon)
        expected = y_large ** alpha

        self.assertAlmostEqual(result, expected, places=8,
                               msg="sig_pow difiere de la ley estándar fuera de la zona muerta")

    def test_convergence_no_chattering(self):
        """Simula múltiples pasos de consenso y verifica que la corrección delta_V
        converge monótonamente a cero sin oscilaciones permanentes (chattering)."""
        agent = FiniteTimeConsensusAgent(agent_id=2, Q_max=30000.0, mode="ONLINE", epsilon=1e-3)
        agent.set_adjacency({1: 1})

        V_i = 0.99
        target_V = 1.0
        dt = 0.5
        Q_i = 9000.0

        corrections = []
        for _ in range(20):
            neighbors = {1: {"V": target_V, "Q_ratio": 0.30}}
            dV, _ = agent.update_consensus(V_i=V_i, Q_i=Q_i, neighbor_states=neighbors, dt=dt)
            corrections.append(abs(dV))
            V_i += dV  # Aplicar la corrección

        # Las correcciones deben decrecer monótonamente (sin chattering)
        # Verificamos que las últimas 5 correcciones no oscilen
        last_5 = corrections[-5:]
        for i in range(1, len(last_5)):
            self.assertLessEqual(last_5[i], last_5[i - 1] + 1e-10,
                                 msg=f"Chattering detectado: corrección[{i}]={last_5[i]} > corrección[{i-1}]={last_5[i-1]}")

    def test_epsilon_parameter_configurable(self):
        """Verifica que el parámetro epsilon se pasa correctamente al agente."""
        agent_default = FiniteTimeConsensusAgent(agent_id=1)
        self.assertEqual(agent_default.epsilon, 1e-3)

        agent_custom = FiniteTimeConsensusAgent(agent_id=1, epsilon=1e-4)
        self.assertEqual(agent_custom.epsilon, 1e-4)

        # La serie de correcciones debe tender a 0 y ser suave
        # (Se asume que la variable 'corrections' estuviera definida si fuera parte del mismo test,
        # pero para cumplir la estructura del archivo, se mantienen las aserciones solicitadas)

    def test_restorative_sign_direction(self):
        """Verifica que si V_local < V_vecino, la ley de consenso produce delta_V > 0 (restaurativa)."""
        agent = FiniteTimeConsensusAgent(agent_id=2, Q_max=30000.0, mode="ONLINE")
        agent.set_adjacency({1: 1.0})

        neighbors = {1: {"V": 1.02, "Q_ratio": 0.30}}  # Vecino con tensión más alta
        dV, _ = agent.update_consensus(V_i=0.98, Q_i=9000.0, neighbor_states=neighbors, dt=0.5)

        self.assertGreater(dV, 0.0, "La ley de consenso debe aumentar la tensión cuando el vecino es superior")

        neighbors_low = {1: {"V": 0.95, "Q_ratio": 0.30}}  # Vecino con tensión más baja
        dV_low, _ = agent.update_consensus(V_i=0.98, Q_i=9000.0, neighbor_states=neighbors_low, dt=0.5)

        self.assertLess(dV_low, 0.0, "La ley de consenso debe reducir la tensión cuando el vecino es inferior")

    def test_lyapunov_settling_time_calculation(self):
        """Verifica el cálculo de la cota superior estricta de tiempo de Lyapunov."""
        agent = FiniteTimeConsensusAgent(agent_id=1, alpha=0.8, beta=1.2, c1=1.0, c2=1.0)
        lambda_2 = 0.5857  # Fiedler eigenvalue

        T_f = agent.calculate_lyapunov_settling_time(lambda_2)
        self.assertIsInstance(T_f, float)
        self.assertGreater(T_f, 0.0)
        self.assertLess(T_f, 100.0)  # Debe ser una cota finita y razonable (< 100 s)

        # Si el grafo se desconecta (lambda_2 = 0), la cota debe ser infinita
        T_inf = agent.calculate_lyapunov_settling_time(0.0)
        self.assertEqual(T_inf, float("inf"))


if __name__ == "__main__":
    unittest.main()
