import math
from typing import Dict, Optional, Tuple, Any

def sig_pow(y: float, gamma: float, epsilon: float = 1e-3) -> float:
    """Calcula la función no lineal sig(y)^gamma = sign(y) * |y|^gamma.

    Implementa una transición suave a un controlador lineal proporcional cuando
    el error |y| es inferior al umbral epsilon. Esto elimina el chattering
    numérico causado por la pendiente infinita de sig(y)^alpha (alpha < 1)
    cerca del origen bajo discretización de Euler explícito.

    Transición suave:
        Si |y| >= epsilon:  sig(y)^gamma = sign(y) * |y|^gamma   (no lineal estándar)
        Si |y| <  epsilon:  sig(y)^gamma ≈ k_p * y               (lineal proporcional)
        donde k_p = epsilon^(gamma - 1) garantiza continuidad C0 en y = ±epsilon.

    Parámetros:
        y:       Error de consenso (escalar).
        gamma:   Exponente de la función no lineal (alpha < 1 o beta > 1).
        epsilon: Umbral de zona muerta adaptativa [default: 1e-3].

    Retorna:
        Valor de la función de control no lineal o su aproximación lineal.
    """
    if abs(y) < 1e-12:
        return 0.0

    sign = 1.0 if y > 0 else -1.0

    if abs(y) < epsilon:
        k_p = epsilon ** (gamma - 1.0)
        return k_p * y
    else:
        return sign * (abs(y) ** gamma)

class FiniteTimeConsensusAgent:
    """
    Agente de Control Secundario Distribuido basado en Consenso en Tiempo Finito Resiliente a Red.
    Regula tensión V_i y garantiza el reparto proporcional de potencia reactiva Q_i / Q_max_i.

    Soporta dos modos de operación:
      - ONLINE (Conectado a Red): El nodo slack principal de la red es dictado por la subestación.
      - OFFLINE (Modo Isla): El nodo Diésel actúa como líder de tensión/frecuencia de la isla.

    Mitigaciones Ciberfísicas y Robustez:
      1. Zona Muerta Adaptativa (Anti-Chattering): Suavizado de la ley no lineal cerca del equilibrio.
      2. Buffer de Frescura Temporal (State Age Tracking): Manejo de paquetes perdidos y retardo mediante
         Zero-Order Hold con tiempo de expiración (max_stale_steps). Si un vecino supera el límite sin reportar,
         se desconecta temporalmente del cálculo (a_ij(t) = 0).
      3. Saturación Anti-Windup: Límites estrictos en delta_V y delta_Q para respetar la capacidad del inversor.
    """
    def __init__(
        self,
        agent_id: int,
        Q_max: float = 50000.0,
        alpha: float = 0.8,
        beta: float = 1.2,
        c1: float = 1.0,
        c2: float = 1.0,
        mode: str = "ONLINE",
        epsilon: float = 1e-3,
        max_delta_V: float = 0.10,      # Saturación máxima de tensión [p.u.] (+/- 10%)
        max_stale_steps: int = 4        # Máximo de pasos reteniendo estado antes de declarar enlace caído
    ):
        self.agent_id = agent_id
        self.Q_max = max(1e-3, Q_max)
        self.alpha = alpha            # 0 < alpha < 1 para convergencia rápida cerca del origen
        self.beta = beta              # beta > 1 para convergencia rápida lejos del origen
        self.c1 = c1
        self.c2 = c2
        self.mode = mode.upper()
        self.epsilon = epsilon
        self.max_delta_V = max_delta_V
        self.max_stale_steps = max_stale_steps

        self.adj_vector: Dict[int, float] = {}  # Dict {neighbor_id: weight} (Matriz de adyacencia A)
        self.V_ref = 1.0                        # Referencia nominal de tensión (p.u.)
        self.delta_V = 0.0                      # Corrección de tensión calculada por el agente
        self.delta_Q = 0.0                      # Corrección de potencia reactiva

        # Buffer de estados de vecinos y edad del dato (en pasos)
        # {neighbor_id: {"state": {"V": ..., "Q_ratio": ...}, "age": int}}
        self.neighbor_buffer: Dict[int, Dict[str, Any]] = {}

    def set_adjacency(self, adj_dict: Dict[int, float]):
        """Define las conexiones de comunicación directa con agentes vecinos."""
        self.adj_vector = adj_dict

    def receive_neighbor_update(self, neighbor_id: int, state: Dict[str, float]):
        """Registra un nuevo paquete de estado recibido desde un vecino, reseteando su edad a 0."""
        self.neighbor_buffer[neighbor_id] = {
            "state": state,
            "age": 0
        }

    def _update_buffer_ages(self, newly_received_ids: set):
        """Incrementa la edad de los datos de vecinos que no enviaron actualización en este paso."""
        for n_id in list(self.neighbor_buffer.keys()):
            if n_id not in newly_received_ids:
                self.neighbor_buffer[n_id]["age"] += 1
                # Si excede el tiempo de frescura, descartar para evitar desestabilización
                if self.neighbor_buffer[n_id]["age"] > self.max_stale_steps:
                    del self.neighbor_buffer[n_id]

    def update_consensus(
        self,
        V_i: float,
        Q_i: float,
        neighbor_states: Optional[Dict[int, Dict[str, float]]] = None,
        dt: float = 0.5
    ) -> Tuple[float, float]:
        """
        Ejecuta un paso del algoritmo de consenso en tiempo finito con tolerancia a fallos de red.

        Parámetros:
            V_i:             Tensión actual medida en la barra i [p.u.]
            Q_i:             Potencia reactiva actual inyectada por la fuente i [VAR]
            neighbor_states: Dict opcional con los estados recién recibidos {neighbor_id: {"V": ..., "Q_ratio": ...}}
            dt:              Paso de tiempo de integración [s] (default: 500 ms)

        Retorna:
            delta_V_i, delta_Q_i (valores saturados y protegidos contra windup)
        """
        received_ids = set()
        if neighbor_states is not None:
            for n_id, state in neighbor_states.items():
                self.receive_neighbor_update(n_id, state)
                received_ids.add(n_id)

        # Envejecer estados de vecinos que no reportaron en este ciclo
        self._update_buffer_ages(received_ids)

        q_ratio_i = Q_i / self.Q_max

        u_v = 0.0
        u_q = 0.0

        # Iterar sobre los vecinos configurados en la matriz de adyacencia
        for n_id, weight in self.adj_vector.items():
            if weight <= 0 or n_id not in self.neighbor_buffer:
                continue

            buffered_data = self.neighbor_buffer[n_id]
            stale_age = buffered_data["age"]

            # Ponderación adaptativa por frescura del dato: decaimiento suave si el dato está envejecido
            freshness_factor = max(0.2, 1.0 - (stale_age / (self.max_stale_steps + 1)))
            effective_weight = weight * freshness_factor

            v_j = buffered_data["state"].get("V", 1.0)
            q_ratio_j = buffered_data["state"].get("Q_ratio", 0.0)

            e_v = V_i - v_j
            e_q = q_ratio_i - q_ratio_j

            term_v = (self.c1 * sig_pow(e_v, self.alpha, self.epsilon)
                      + self.c2 * sig_pow(e_v, self.beta, self.epsilon))
            term_q = (self.c1 * sig_pow(e_q, self.alpha, self.epsilon)
                      + self.c2 * sig_pow(e_q, self.beta, self.epsilon))

            u_v += effective_weight * term_v
            u_q += effective_weight * term_q

        # Modo OFFLINE (Isla) y este agente es el Diésel (Líder de tensión de la microrred)
        if self.mode == "OFFLINE" and self.agent_id == 1:
            e_leader = V_i - self.V_ref
            # El líder fija estrictamente la referencia nominal de tensión de la isla
            u_v = self.c1 * sig_pow(e_leader, self.alpha, self.epsilon)

        # Cálculo de la corrección incremental de control (Paso de Euler: Delta V_i = -dt * u_v)
        # El llamador integra este incremento en el voltaje/potencia (V_i += dV, Q_i += dQ)
        raw_delta_V = -dt * u_v
        raw_delta_Q = -dt * u_q * self.Q_max

        # Saturación Anti-Windup en los límites de capacidad
        self.delta_V = max(-self.max_delta_V, min(self.max_delta_V, raw_delta_V))
        self.delta_Q = max(-self.Q_max, min(self.Q_max, raw_delta_Q))

        return self.delta_V, self.delta_Q

if __name__ == "__main__":
    agent = FiniteTimeConsensusAgent(agent_id=2, Q_max=30000.0, mode="ONLINE")
    agent.set_adjacency({1: 1.0, 3: 1.0})

    neighbors = {
        1: {"V": 1.00, "Q_ratio": 0.20},
        3: {"V": 0.98, "Q_ratio": 0.40}
    }
    dV, dQ = agent.update_consensus(V_i=0.99, Q_i=9000.0, neighbor_states=neighbors, dt=0.5)
    print(f"Agente 2 Consenso Resiliente: delta_V = {dV:.6f} p.u., delta_Q = {dQ:.2f} VAR")
