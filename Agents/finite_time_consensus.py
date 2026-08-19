import math

def sig_pow(y, gamma):
    """Calcula la función no lineal sig(y)^gamma = sign(y) * |y|^gamma."""
    if abs(y) < 1e-9:
        return 0.0
    sign = 1.0 if y > 0 else -1.0
    return sign * (abs(y) ** gamma)

class FiniteTimeConsensusAgent:
    """
    Agente de Control Secundario Distribuido basado en Consenso en Tiempo Finito.
    Regula tensión V_i y garantiza el reparto proporcional de potencia reactiva Q_i / Q_max_i.
    
    Soporta dos modos de operación:
      - ONLINE (Conectado a Red): El nodo slack principal de la red es dictado por la subestación.
      - OFFLINE (Modo Isla): El nodo Diésel actúa como líder de tensión/frecuencia de la isla.
    """
    def __init__(self, agent_id, Q_max=50000.0, alpha=0.8, beta=1.2, c1=1.0, c2=1.0, mode="ONLINE"):
        self.agent_id = agent_id
        self.Q_max = Q_max
        self.alpha = alpha            # 0 < alpha < 1 para convergencia rápida cerca del origen
        self.beta = beta              # beta > 1 para convergencia rápida lejos del origen
        self.c1 = c1
        self.c2 = c2
        self.mode = mode.upper()
        self.adj_vector = {}          # Dict {neighbor_id: weight} (Matriz de adyacencia A)
        self.V_ref = 1.0              # Referencia nominal de tensión (p.u.)
        self.delta_V = 0.0            # Corrección de tensión calculada por el agente
        self.delta_Q = 0.0            # Corrección de potencia reactiva

    def set_adjacency(self, adj_dict):
        """Define las conexiones de comunicación directa con agentes vecinos."""
        self.adj_vector = adj_dict

    def update_consensus(self, V_i, Q_i, neighbor_states, dt=0.5):
        """
        Ejecuta un paso del algoritmo de consenso en tiempo finito.

        Implementa la discretización de Euler explícito de la ley de control continua:
            ẋᵢ = -c₁·sig(eᵢ)^α - c₂·sig(eᵢ)^β
        → x_{k+1} = x_k + dt · u_k
        
        Parámetros:
            V_i:             Tensión actual medida en la barra i [p.u.]
            Q_i:             Potencia reactiva actual inyectada por la fuente i [VAR]
            neighbor_states: Dict {neighbor_id: {"V": V_j, "Q_ratio": Q_j/Q_max_j}}
            dt:              Paso de tiempo de integración [s]. Default 0.5 s (500 ms del reloj maestro).
            
        Retorna:
            delta_V_i, delta_Q_i
        """
        # Ratio de potencia reactiva local
        q_ratio_i = Q_i / self.Q_max if self.Q_max > 0 else 0.0

        u_v = 0.0
        u_q = 0.0

        for n_id, weight in self.adj_vector.items():
            if weight <= 0 or n_id not in neighbor_states:
                continue

            v_j = neighbor_states[n_id].get("V", 1.0)
            q_ratio_j = neighbor_states[n_id].get("Q_ratio", 0.0)

            # Error de tensión entre vecinos
            e_v = V_i - v_j
            # Error de ratio de potencia reactiva entre vecinos
            e_q = q_ratio_i - q_ratio_j

            # Ley de control no lineal de tiempo finito para tensión y potencia reactiva
            term_v = self.c1 * sig_pow(e_v, self.alpha) + self.c2 * sig_pow(e_v, self.beta)
            term_q = self.c1 * sig_pow(e_q, self.alpha) + self.c2 * sig_pow(e_q, self.beta)

            u_v += weight * term_v
            u_q += weight * term_q

        # Si el modo es OFFLINE (Isla) y este agente es el Diésel (Nodo 1 Líder), fija la tensión
        if self.mode == "OFFLINE" and self.agent_id == 1:
            e_leader = V_i - self.V_ref
            u_v += self.c1 * sig_pow(e_leader, self.alpha)

        # Actualizar correcciones integrales — Euler explícito: x_{k+1} = x_k + dt·u
        # El signo negativo aplica la ley de control reguladora (llevar error a cero)
        self.delta_V = -dt * u_v
        self.delta_Q = -dt * u_q * self.Q_max

        return self.delta_V, self.delta_Q

if __name__ == "__main__":
    agent = FiniteTimeConsensusAgent(agent_id=2, Q_max=30000.0, mode="ONLINE")
    agent.set_adjacency({1: 1, 3: 1})  # Conectado a Nodo 1 y Nodo 3
    
    neighbors = {
        1: {"V": 1.00, "Q_ratio": 0.20},
        3: {"V": 0.98, "Q_ratio": 0.40}
    }
    # dt=0.5 corresponde al paso maestro de co-simulación de 500 ms
    dV, dQ = agent.update_consensus(V_i=0.99, Q_i=9000.0, neighbor_states=neighbors, dt=0.5)
    print(f"Prueba Agente 2 Consenso Finito (Modo ONLINE): delta_V = {dV:.6f} p.u., delta_Q = {dQ:.2f} VAR")
