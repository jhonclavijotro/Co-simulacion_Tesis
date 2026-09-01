import math
import numpy as np
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


class FixedTimeConsensusAgent:
    """
    Agente de Control Secundario Distribuido basado en Consenso en Tiempo Fijo (FxTS) Resiliente a Red.
    Regula la tensión local V_i y garantiza el reparto proporcional de potencia reactiva Q_i / Q_max_i.

    Fundamentación Teórica:
      Ecuación de consenso restaurativo de doble potencia fraccionaria (FxTS):
        u_v,i = sum_{j in N_i} a_ij * [ c1 * sig(V_j - V_i)^alpha + c2 * sig(V_j - V_i)^beta ]
        u_q,i = sum_{j in N_i} a_ij * [ c1 * sig(q_ratio_j - q_ratio_i)^alpha + c2 * sig(q_ratio_j - q_ratio_i)^beta ]
      donde 0 < alpha < 1 acelera la convergencia fina cerca de cero y beta > 1 acelera ante grandes desvíos.

    Soporta dos modos de operación:
      - ONLINE (Conectado a Red): El nodo slack principal es dictado por la subestación.
      - OFFLINE (Modo Isla): El nodo Diésel actúa como líder de fijación de tensión/frecuencia (pinning).

    Mitigaciones Ciberfísicas y Robustez:
      1. Zona Muerta Adaptativa (Anti-Chattering): Suavizado de la ley no lineal cerca del equilibrio (|e| < epsilon).
      2. Buffer de Frescura Temporal (State Age Tracking): Manejo de paquetes perdidos y retardo mediante
         retención ZOH con tiempo de expiración (max_stale_steps). Si un enlace expira, a_ij(t) = 0.
      3. Saturación Anti-Windup: Límites estrictos en delta_V (+/-10%) y delta_Q (+/-Q_max).
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
        self.agent_id = int(agent_id)
        self.Q_max = max(1e-3, float(Q_max))
        self.alpha = float(alpha)      # 0 < alpha < 1
        self.beta = float(beta)        # beta > 1
        self.c1 = float(c1)
        self.c2 = float(c2)
        self.mode = mode.upper()
        self.epsilon = float(epsilon)
        self.max_delta_V = float(max_delta_V)
        self.max_stale_steps = int(max_stale_steps)

        self.adj_vector: Dict[int, float] = {}  # Dict {neighbor_id: weight} (Fila i de Matriz de adyacencia A)
        self.V_ref = 1.0                        # Referencia nominal de tensión [p.u.]
        self.delta_V = 0.0                      # Offset de tensión acumulado
        self.delta_Q = 0.0                      # Offset de potencia reactiva acumulado

        # Buffer de estados de vecinos y edad del dato (en pasos)
        # {neighbor_id: {"state": {"V": ..., "Q_ratio": ...}, "age": int}}
        self.neighbor_buffer: Dict[int, Dict[str, Any]] = {}

    def set_adjacency(self, adj_dict: Dict[int, float]):
        """Define las conexiones de comunicación directa con agentes vecinos."""
        self.adj_vector = {int(k): float(v) for k, v in adj_dict.items()}

    def receive_neighbor_update(self, neighbor_id: int, state: Dict[str, float]):
        """Registra un nuevo paquete de estado recibido desde un vecino, reseteando su edad a 0."""
        self.neighbor_buffer[int(neighbor_id)] = {
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
        Ejecuta un paso del algoritmo de consenso en tiempo fijo con signo restaurativo corregido.

        Parámetros:
            V_i:             Tensión actual medida en la barra i [p.u.]
            Q_i:             Potencia reactiva actual inyectada por la fuente i [VAR]
            neighbor_states: Dict opcional con los estados recién recibidos {neighbor_id: {"V": ..., "Q_ratio": ...}}
            dt:              Paso de tiempo de integración macro [s] (default: 500 ms)

        Retorna:
            delta_V_i, delta_Q_i (valores de corrección saturados y protegidos contra windup)
        """
        received_ids = set()
        if neighbor_states is not None:
            for n_id, state in neighbor_states.items():
                self.receive_neighbor_update(n_id, state)
                received_ids.add(int(n_id))

        # Envejecer estados de vecinos que no reportaron en este ciclo
        self._update_buffer_ages(received_ids)

        q_ratio_i = Q_i / self.Q_max

        u_v = 0.0
        u_q = 0.0

        # Iterar sobre los vecinos configurados en el vector de adyacencia
        for n_id, weight in self.adj_vector.items():
            if weight <= 0 or n_id not in self.neighbor_buffer:
                continue

            buffered_data = self.neighbor_buffer[n_id]
            stale_age = buffered_data["age"]

            # Ponderación adaptativa por frescura del dato
            freshness_factor = max(0.2, 1.0 - (stale_age / (self.max_stale_steps + 1)))
            effective_weight = weight * freshness_factor

            v_j = float(buffered_data["state"].get("V", 1.0))
            q_ratio_j = float(buffered_data["state"].get("Q_ratio", 0.0))

            # Formulación matemática corregida: error restaurativo e = (vecino_j - local_i)
            e_v = v_j - V_i
            e_q = q_ratio_j - q_ratio_i

            term_v = (self.c1 * sig_pow(e_v, self.alpha, self.epsilon)
                      + self.c2 * sig_pow(e_v, self.beta, self.epsilon))
            term_q = (self.c1 * sig_pow(e_q, self.alpha, self.epsilon)
                      + self.c2 * sig_pow(e_q, self.beta, self.epsilon))

            u_v += effective_weight * term_v
            u_q += effective_weight * term_q

        # Modo OFFLINE (Isla) y este agente es el Diésel (Líder / Pinning de tensión de la microrred)
        if self.mode == "OFFLINE" and self.agent_id == 1:
            e_leader = self.V_ref - V_i
            u_v += (self.c1 * sig_pow(e_leader, self.alpha, self.epsilon)
                    + self.c2 * sig_pow(e_leader, self.beta, self.epsilon))

        # Cálculo de la corrección incremental de control restaurativo (+dt * u)
        raw_delta_V = dt * u_v
        raw_delta_Q = dt * u_q * self.Q_max

        # Saturación Anti-Windup en los límites de capacidad
        self.delta_V = max(-self.max_delta_V, min(self.max_delta_V, raw_delta_V))
        self.delta_Q = max(-self.Q_max, min(self.Q_max, raw_delta_Q))

        return self.delta_V, self.delta_Q

    def calculate_lyapunov_settling_time(self, lambda_2: float) -> float:
        """Calcula la cota superior analítica estricta de tiempo de asentamiento de Lyapunov (T_f).

        Fórmula de Lyapunov para grafos no dirigidos (Zuo & Tie, 2016; Polyakov, 2012):
            T_f <= 2^((1-alpha)/2) / [ c1 * (1 - alpha) * lambda_2^((1+alpha)/2) ]
                 + 2^((1-beta)/2)  / [ c2 * (beta - 1)  * lambda_2^((1+beta)/2) ]

        Parámetros:
            lambda_2: Conectividad algebraica (autovalor de Fiedler) de la matriz Laplaciana L.

        Retorna:
            Cota superior del tiempo de convergencia T_f [segundos].
        """
        if lambda_2 <= 1e-6:
            return float("inf")

        t1 = (2.0 ** ((1.0 - self.alpha) / 2.0)) / (
            self.c1 * (1.0 - self.alpha) * (lambda_2 ** ((1.0 + self.alpha) / 2.0))
        )
        t2 = (2.0 ** ((1.0 - self.beta) / 2.0)) / (
            self.c2 * (self.beta - 1.0) * (lambda_2 ** ((1.0 + self.beta) / 2.0))
        )
        return t1 + t2


# Alias retrocompatible para clases existentes en el proyecto
FiniteTimeConsensusAgent = FixedTimeConsensusAgent


if __name__ == "__main__":
    agent = FixedTimeConsensusAgent(agent_id=2, Q_max=30000.0, mode="ONLINE")
    agent.set_adjacency({1: 1.0, 3: 1.0})

    neighbors = {
        1: {"V": 1.00, "Q_ratio": 0.20},
        3: {"V": 0.98, "Q_ratio": 0.40}
    }
    dV, dQ = agent.update_consensus(V_i=0.99, Q_i=9000.0, neighbor_states=neighbors, dt=0.5)
    fiedler_val = 0.5857  # Autovalor de Fiedler para la red de 4 nodos lineal
    t_settle = agent.calculate_lyapunov_settling_time(fiedler_val)
    print(f"Agente 2 Consenso FxTS: delta_V = {dV:.6f} p.u., delta_Q = {dQ:.2f} VAR")
    print(f"Cota Estricta de Lyapunov (Fiedler={fiedler_val}): T_f <= {t_settle:.2f} s")
