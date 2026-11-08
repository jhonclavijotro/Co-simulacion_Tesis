import csv
import hashlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Agents.network_impairment_proxy import NetworkImpairmentProxy
from Agents.fixed_time_consensus import FixedTimeConsensusAgent
from Agents.distributed_node_runner import DistributedNodeRunner

class TestTelemetryResilience(unittest.TestCase):
    """
    Suite de verificación para S-34: Campaña de resiliencia telemática,
    contrato normativo D-25 (Anexo O-10) e integración de proxy de perturbaciones en runners.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_d25_csv_ingestion_and_deterministic_seed_derivation(self):
        """Verifica la carga del archivo CSV D-25 (14 columnas) y la fórmula de semilla por celda."""
        csv_path = os.path.join(self.temp_dir.name, "contingencias_test.csv")
        headers = [
            "id", "tipo", "alcance", "origen", "destino", "inicio_s", "fin_s",
            "param_min", "param_max", "unidad", "modelo", "reintento_s", "semilla", "justificacion"
        ]
        rows = [
            # F1: Latencia creciente global 50 -> 500 ms en t in [100, 200]
            ["F1", "latencia", "global", "", "", "100.0", "200.0", "50.0", "500.0", "ms", "", "5.0", "", "Actividad 3.3"],
            # F2: Pérdida dirigida enlace 2 -> 3 de 15% en t in [200, 300]
            ["F2", "perdida", "enlace", "2", "3", "200.0", "300.0", "0.15", "0.15", "fraccion", "bernoulli", "5.0", "", "Actividad 3.3"],
            # F2_rev: Pérdida dirigida enlace 3 -> 2 de 15% en t in [200, 300]
            ["F2", "perdida", "enlace", "3", "2", "200.0", "300.0", "0.15", "0.15", "fraccion", "bernoulli", "5.0", "", "Actividad 3.3"],
            # F3: Desconexión dirigida enlace 2 -> 3 en t in [220, 260]
            ["F3", "desconexion", "enlace", "2", "3", "220.0", "260.0", "", "", "", "", "5.0", "", "Partición transitoria"]
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)

        base_seed = 42
        proxy = NetworkImpairmentProxy(profile="IDEAL", seed=base_seed)
        proxy.load_contingencies_csv(csv_path, semilla_base=base_seed)

        self.assertEqual(len(proxy.contingencies), 4)

        # Verificar derivación determinista de semillas
        # Enlace 2->3 vs 3->2 deben tener semillas diferentes
        expected_seed_2_3 = hashlib.sha256(f"{base_seed}|F2|2|3".encode("utf-8")).hexdigest()[:8]
        expected_seed_3_2 = hashlib.sha256(f"{base_seed}|F2|3|2".encode("utf-8")).hexdigest()[:8]
        self.assertNotEqual(expected_seed_2_3, expected_seed_3_2)

        cont_f2_23 = [c for c in proxy.contingencies if c["id"] == "F2" and c["origen"] == 2 and c["destino"] == 3][0]
        cont_f2_32 = [c for c in proxy.contingencies if c["id"] == "F2" and c["origen"] == 3 and c["destino"] == 2][0]
        self.assertEqual(cont_f2_23["semilla"], expected_seed_2_3)
        self.assertEqual(cont_f2_32["semilla"], expected_seed_3_2)

    def test_latency_ramp_evaluation(self):
        """Verifica que una contingencia de latencia evalúe la rampa param_min -> param_max temporalmente."""
        proxy = NetworkImpairmentProxy(profile="IDEAL", seed=10)
        proxy.add_contingency(
            c_id="F1",
            tipo="latencia",
            alcance="global",
            inicio_s=100.0,
            fin_s=200.0,
            param_min=50.0,
            param_max=500.0,
            unidad="ms"
        )

        raw_state = {2: {"V": 1.0, "Q_ratio": 0.5}}

        # Antes de inicio_s (t = 50 s): canal IDEAL (latencia = 0)
        _, meta_pre = proxy.filter_neighbor_states(receiver_id=1, raw_neighbor_states=raw_state, current_time_s=50.0)
        self.assertEqual(meta_pre["falla_activa"], False)
        self.assertEqual(meta_pre["latencias_ms"][2], 0.0)

        # En t = 100 s (inicio de rampa): latencia ~ 50 ms
        _, meta_t100 = proxy.filter_neighbor_states(receiver_id=1, raw_neighbor_states=raw_state, current_time_s=100.0)
        self.assertEqual(meta_t100["falla_activa"], True)
        self.assertEqual(meta_t100["active_contingencies"], ["F1"])
        self.assertAlmostEqual(meta_t100["latencias_ms"][2], 50.0, delta=1.0)

        # En t = 150 s (punto medio de rampa): latencia ~ 275 ms
        _, meta_t150 = proxy.filter_neighbor_states(receiver_id=1, raw_neighbor_states=raw_state, current_time_s=150.0)
        self.assertAlmostEqual(meta_t150["latencias_ms"][2], 275.0, delta=1.0)

        # En t = 200 s (final de rampa / expiración): retorna a IDEAL
        _, meta_t200 = proxy.filter_neighbor_states(receiver_id=1, raw_neighbor_states=raw_state, current_time_s=200.0)
        self.assertEqual(meta_t200["falla_activa"], False)

    def test_link_disconnection_and_stale_buffer_hold_last_value(self):
        """
        Verifica que una desconexión de enlace active la retención ZOH en FixedTimeConsensusAgent,
        incremente el tiempo de frescura y luego restablezca el consenso al reconectar.
        """
        proxy = NetworkImpairmentProxy(profile="IDEAL", seed=42)
        # Desconectar enlace 2 -> 1 entre t = 10s y t = 13s (pasos k=20 a k=26)
        proxy.add_contingency(
            c_id="F3_TEST",
            tipo="desconexion",
            alcance="enlace",
            origen=2,
            destino=1,
            inicio_s=10.0,
            fin_s=13.0
        )

        agent = FixedTimeConsensusAgent(agent_id=1, Q_max=20000.0, P_max=50000.0, max_stale_steps=4)
        agent.set_adjacency({2: 1.0})

        # Paso 1: t = 9.0s (Canal saludable)
        raw_state = {2: {"V": 1.02, "Q_ratio": 0.40, "omega": 376.99, "P_ratio": 0.30}}
        filt_1, meta_1 = proxy.filter_neighbor_states(receiver_id=1, raw_neighbor_states=raw_state, current_time_s=9.0)
        self.assertIn(2, filt_1)
        agent.update_consensus(V_i=1.0, Q_i=8000.0, neighbor_states=filt_1, dt=0.5)
        self.assertIn(2, agent.neighbor_buffer)
        self.assertEqual(agent.neighbor_buffer[2]["age"], 0)

        # Paso 2: t = 10.5s (Enlace desconectado) -> paquete descartado
        filt_2, meta_2 = proxy.filter_neighbor_states(receiver_id=1, raw_neighbor_states=raw_state, current_time_s=10.5)
        self.assertNotIn(2, filt_2)
        self.assertEqual(meta_2["dropped"], 1)
        # El agente actualiza consenso sin nuevos estados: el buffer ZOH retiene el valor anterior con age=1
        agent.update_consensus(V_i=1.0, Q_i=8000.0, neighbor_states=filt_2, dt=0.5)
        self.assertIn(2, agent.neighbor_buffer)
        self.assertEqual(agent.neighbor_buffer[2]["age"], 1)

        # Paso 3: t = 11.0s (Sigue desconectado) -> age=2
        filt_3, _ = proxy.filter_neighbor_states(receiver_id=1, raw_neighbor_states=raw_state, current_time_s=11.0)
        agent.update_consensus(V_i=1.0, Q_i=8000.0, neighbor_states=filt_3, dt=0.5)
        self.assertEqual(agent.neighbor_buffer[2]["age"], 2)

        # Paso 4: t = 13.5s (Enlace reconectado) -> paquete entregado y age reseteado a 0
        filt_4, meta_4 = proxy.filter_neighbor_states(receiver_id=1, raw_neighbor_states=raw_state, current_time_s=13.5)
        self.assertIn(2, filt_4)
        self.assertEqual(meta_4["delivered"], 1)
        agent.update_consensus(V_i=1.0, Q_i=8000.0, neighbor_states=filt_4, dt=0.5)
        self.assertEqual(agent.neighbor_buffer[2]["age"], 0)

    def test_full_300s_resilience_campaign_simulation(self):
        """
        Ensayo formal de 300 s (601 pasos a dt=0.5s) con los tres tramos de resiliencia:
          - Tramo 1 (0-100 s): Canal IDEAL.
          - Tramo 2 (100-200 s): Latencia creciente 50 -> 500 ms (F1).
          - Tramo 3 (200-300 s): Pérdida de paquetes 10-30% (F2) y desconexión temporal de enlace (F3).
        Verifica convergencia, estabilidad de tensión y recuperación de consenso tras falla.
        """
        proxy = NetworkImpairmentProxy(profile="IDEAL", seed=42)
        # F1: Latencia global creciente 50 a 500 ms en [100, 200] s
        proxy.add_contingency(
            c_id="F1", tipo="latencia", alcance="global",
            inicio_s=100.0, fin_s=200.0, param_min=50.0, param_max=500.0, unidad="ms"
        )
        # F2: Pérdida dirigida enlace 2 -> 3 de 20% en [200, 300] s
        proxy.add_contingency(
            c_id="F2", tipo="perdida", alcance="enlace",
            origen=2, destino=3, inicio_s=200.0, fin_s=300.0, param_min=0.20, param_max=0.20,
            unidad="fraccion", modelo="bernoulli"
        )
        # F3: Desconexión dirigida enlace 1 <-> 2 en [220, 240] s (20 s de corte)
        proxy.add_contingency(
            c_id="F3_12", tipo="desconexion", alcance="enlace",
            origen=1, destino=2, inicio_s=220.0, fin_s=240.0
        )
        proxy.add_contingency(
            c_id="F3_21", tipo="desconexion", alcance="enlace",
            origen=2, destino=1, inicio_s=220.0, fin_s=240.0
        )

        # 3 Agentes DER en línea: 1 (Diesel/Slack) <-> 2 (Solar) <-> 3 (BESS)
        agents = {
            1: FixedTimeConsensusAgent(agent_id=1, Q_max=30000.0, P_max=50000.0, mode="OFFLINE", c1=0.25, c2=0.15, max_stale_steps=4),
            2: FixedTimeConsensusAgent(agent_id=2, Q_max=20000.0, P_max=40000.0, mode="OFFLINE", c1=0.25, c2=0.15, max_stale_steps=4),
            3: FixedTimeConsensusAgent(agent_id=3, Q_max=15000.0, P_max=20000.0, mode="OFFLINE", c1=0.25, c2=0.15, max_stale_steps=4)
        }
        agents[1].set_adjacency({2: 1.0})
        agents[2].set_adjacency({1: 1.0, 3: 1.0})
        agents[3].set_adjacency({2: 1.0})

        voltages = {1: 1.02, 2: 0.95, 3: 0.94}
        q_injections = {1: 15000.0, 2: 5000.0, 3: 4000.0}

        steps = 600  # 300 s a dt=0.5 s
        dt = 0.5
        total_dropped = 0
        total_delivered = 0

        for k in range(1, steps + 1):
            t_s = round(k * dt, 2)

            current_states = {
                i: {
                    "V": voltages[i],
                    "Q_ratio": q_injections[i] / agents[i].Q_max,
                    "omega": 376.99,
                    "P_ratio": 0.5
                }
                for i in agents
            }

            for i, agent in agents.items():
                raw_n = {nid: current_states[nid] for nid in agent.adj_vector}
                filt_n, d_meta = proxy.filter_neighbor_states(
                    receiver_id=i,
                    raw_neighbor_states=raw_n,
                    current_step=k,
                    current_time_s=t_s
                )
                total_dropped += d_meta["dropped"]
                total_delivered += d_meta["delivered"]

                dV, dQ = agent.update_consensus(
                    V_i=voltages[i],
                    Q_i=q_injections[i],
                    neighbor_states=filt_n,
                    dt=dt
                )
                voltages[i] = max(0.85, min(1.15, voltages[i] + dV))
                q_injections[i] = max(0.0, min(agent.Q_max, q_injections[i] + dQ))

        # Verificaciones del ensayo de resiliencia:
        # 1. Se registraron entregas y caídas por contingencias
        self.assertGreater(total_delivered, 0)
        self.assertGreater(total_dropped, 0)

        # 2. Las tensiones finales deben estar dentro del margen normativo [0.95, 1.05] p.u.
        for nid, v_val in voltages.items():
            self.assertGreaterEqual(v_val, 0.95, f"Nodo {nid} bajo tensión: {v_val}")
            self.assertLessEqual(v_val, 1.05, f"Nodo {nid} sobre tensión: {v_val}")

        # 3. Discrepancia final de reactiva (reparto proporcional) tras reconexión debe ser pequeña
        ratios = [q_injections[i] / agents[i].Q_max for i in agents]
        max_q_err = max(ratios) - min(ratios)
        self.assertLess(max_q_err, 0.05, f"Discrepancia reactiva post-reconexión excedida: {max_q_err}")

    def test_distributed_node_runner_impairment_configuration(self):
        """Verifica que DistributedNodeRunner instancie el proxy y acepte argumentos telemáticos."""
        runner = DistributedNodeRunner(
            node_id=2,
            source_type="SOLAR",
            master_host="127.0.0.1",
            p2p_port=6410,
            port_rep=6411,
            port_pub=6412,
            network_profile="INDUSTRIAL_WIFI",
            network_seed=123
        )
        try:
            self.assertEqual(runner.network_profile, "INDUSTRIAL_WIFI")
            self.assertEqual(runner.network_seed, 123)
            self.assertIsNotNone(runner.impairment_proxy)
            self.assertEqual(runner.impairment_proxy.profile_name, "INDUSTRIAL_WIFI")
            self.assertEqual(runner.neighbor_cache, {})
            self.assertEqual(runner.last_delivery_meta, {})
        finally:
            runner.close()


if __name__ == "__main__":
    unittest.main()
