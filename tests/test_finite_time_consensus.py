import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Agents.finite_time_consensus import FiniteTimeConsensusAgent

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

if __name__ == "__main__":
    unittest.main()
