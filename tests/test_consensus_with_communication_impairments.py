import math
import os
import sys
from typing import Dict, List, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Agents.finite_time_consensus import FiniteTimeConsensusAgent
from Agents.network_impairment_proxy import NetworkImpairmentProxy

def simulate_mas_consensus(
    steps: int = 40,
    network_profile: str = "IDEAL",
    link_outage_event: tuple = None,
    seed: int = 42
) -> Dict[str, Any]:
    """
    Simula una microrred de 4 nodos interactuando bajo control secundario distribuido:
      - Nodo 1: Diésel / Slack (Líder en OFFLINE o ancla en ONLINE)
      - Nodo 2: Solar Fotovoltaico (Seguidor)
      - Nodo 3: Eólica PMSG (Seguidor)
      - Nodo 4: Hidro / BESS (Seguidor)
    
    Topología en línea: 1 <-> 2 <-> 3 <-> 4
    """
    proxy = NetworkImpairmentProxy(profile=network_profile, seed=seed)

    if link_outage_event:
        u, v, start_step, duration = link_outage_event
        proxy.schedule_link_outage(u, v, start_step, duration)

    # Crear agentes con ganancias discretas sintonizadas (c1=0.25, c2=0.15 para polo en z=+0.6 con dt=0.5s)
    agents = {
        1: FiniteTimeConsensusAgent(agent_id=1, Q_max=50000.0, mode="OFFLINE", c1=0.25, c2=0.15),
        2: FiniteTimeConsensusAgent(agent_id=2, Q_max=30000.0, mode="OFFLINE", c1=0.25, c2=0.15),
        3: FiniteTimeConsensusAgent(agent_id=3, Q_max=40000.0, mode="OFFLINE", c1=0.25, c2=0.15),
        4: FiniteTimeConsensusAgent(agent_id=4, Q_max=20000.0, mode="OFFLINE", c1=0.25, c2=0.15)
    }

    # Asignar adyacencia (Línea: 1-2, 2-3, 3-4)
    agents[1].set_adjacency({2: 1.0})
    agents[2].set_adjacency({1: 1.0, 3: 1.0})
    agents[3].set_adjacency({2: 1.0, 4: 1.0})
    agents[4].set_adjacency({3: 1.0})

    # Estados iniciales perturbados
    voltages = {1: 1.03, 2: 0.94, 3: 0.96, 4: 0.92}
    # Potencias reactivas iniciales con ratios desiguales
    q_injections = {1: 30000.0, 2: 6000.0, 3: 28000.0, 4: 15000.0}

    history_V = {i: [] for i in agents}
    history_Q_ratio = {i: [] for i in agents}

    dt = 0.5  # Paso de 500 ms

    for k in range(1, steps + 1):
        # 1. Recolectar estados de salida de cada nodo
        current_states = {}
        for i in agents:
            current_states[i] = {
                "V": voltages[i],
                "Q_ratio": q_injections[i] / agents[i].Q_max
            }
            history_V[i].append(voltages[i])
            history_Q_ratio[i].append(q_injections[i] / agents[i].Q_max)

        # 2. Intercambio P2P a través del proxy de red
        for i, agent in agents.items():
            # Obtener vecinos teóricos de la matriz de adyacencia
            raw_neighbors = {n_id: current_states[n_id] for n_id in agent.adj_vector}
            
            # Filtrar por canal estocástico
            filtered_neighbors, _ = proxy.filter_neighbor_states(
                receiver_id=i,
                raw_neighbor_states=raw_neighbors,
                current_step=k
            )

            # Ejecutar actualización de consenso
            dV, dQ = agent.update_consensus(
                V_i=voltages[i],
                Q_i=q_injections[i],
                neighbor_states=filtered_neighbors,
                dt=dt
            )

            # Dinámica física emulada: aplicar corrección secundaria
            voltages[i] += dV
            q_injections[i] = max(0.0, min(agent.Q_max, q_injections[i] + dQ))

    return {
        "history_V": history_V,
        "history_Q_ratio": history_Q_ratio,
        "final_voltages": {i: history_V[i][-1] for i in agents},
        "final_Q_ratios": {i: history_Q_ratio[i][-1] for i in agents},
        "network_health": proxy.get_network_health()
    }

def test_consensus_ideal_channel():
    res = simulate_mas_consensus(steps=80, network_profile="IDEAL")
    
    # 1. Verificar convergencia de tensión hacia 1.0 p.u. (referencia del líder)
    for node_id, v_final in res["final_voltages"].items():
        assert abs(v_final - 1.0) < 0.02, f"Nodo {node_id} no convergió en V: {v_final}"

    # 2. Verificar consenso en reparto proporcional de potencia reactiva (Q_i / Q_max)
    ratios = list(res["final_Q_ratios"].values())
    max_diff_q = max(ratios) - min(ratios)
    assert max_diff_q < 0.05, f"Discrepancia en Q_ratio superior al umbral: {max_diff_q}"

def test_consensus_under_industrial_wifi():
    """Prueba con latencia de 30ms, jitter y 5% de pérdida de paquetes."""
    res = simulate_mas_consensus(steps=90, network_profile="INDUSTRIAL_WIFI", seed=100)
    
    # A pesar de pérdidas y retardo, el algoritmo debe converger
    for node_id, v_final in res["final_voltages"].items():
        assert abs(v_final - 1.0) < 0.03, f"Nodo {node_id} divergente en WiFi: {v_final}"

    ratios = list(res["final_Q_ratios"].values())
    max_diff_q = max(ratios) - min(ratios)
    assert max_diff_q < 0.08

def test_consensus_under_severe_stress():
    """Prueba con latencia de 150ms, ráfagas Markovianas Gilbert-Elliott y 20% de pérdidas."""
    res = simulate_mas_consensus(steps=100, network_profile="SEVERE_STRESS", seed=200)

    # El buffer de frescura evita inestabilidad numérica
    for node_id, v_final in res["final_voltages"].items():
        assert 0.90 <= v_final <= 1.10, f"Voltaje inestable fuera de banda operativa en estrés: {v_final}"

def test_consensus_under_dynamic_n_minus_1_link_failure():
    """Prueba de corte dinámico del enlace 2 <-> 3 entre pasos 15 y 25 (10 pasos de desconexión)."""
    res = simulate_mas_consensus(
        steps=100,
        network_profile="LAN_ETHERNET",
        link_outage_event=(2, 3, 15, 10),
        seed=300
    )

    # Tras restablecer el enlace en el paso 25, el sistema debe reconverger hacia el consenso global
    for node_id, v_final in res["final_voltages"].items():
        assert abs(v_final - 1.0) < 0.035, f"Nodo {node_id} no recuperó consenso tras falla de enlace: {v_final}"

    ratios = list(res["final_Q_ratios"].values())
    max_diff_q = max(ratios) - min(ratios)
    assert max_diff_q < 0.08
