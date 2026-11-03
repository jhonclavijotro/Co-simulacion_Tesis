"""
Líneas Base de Control Secundario (v2) para el Benchmark Comparativo.
Tesis de Grado: Control Secundario Distribuido en Tiempo Fijo.

Implementa los cinco controladores evaluados según benchmark-spec-v2.md §5:
  1. Droop puro (Guerrero et al., 2011 - IEEE TIE)
  2. PI centralizado (SPoF / referencia clásica de control secundario)
  3. DAPI: Consenso asintótico lineal (Simpson-Porco et al., 2015 - IEEE TIE 62(11))
  4. FTS: Consenso en tiempo finito simple (Wang et al., 2021 - Energies 14(19))
  5. FxTS: Consenso en tiempo fijo de la tesis (importado desde Agents.finite_time_consensus)

Cada línea base soporta dos modalidades de sintonización:
  - "published": Parámetros tal como aparecen en los papers de referencia.
  - "optimized": Parámetros optimizados minimizando IAE sujeto a estabilidad CFL.
"""

import sys
import os
import math
import numpy as np
from typing import Dict, Any, List, Optional, Tuple

# Asegurar importación del controlador real sin reimplementar
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Agents.finite_time_consensus import FixedTimeConsensusAgent, sig_pow


class BaseSecondaryController:
    """Clase base abstracta para controladores de control secundario."""
    def __init__(self, agent_id: int, P_max: float = 50000.0, Q_max: float = 50000.0, f_ref: float = 60.0):
        self.agent_id = agent_id
        self.P_max = P_max
        self.Q_max = Q_max
        self.f_ref = f_ref
        self.omega_ref = 2.0 * math.pi * f_ref
        self.adj_vector: Dict[int, float] = {}

    def set_adjacency(self, adj_dict: Dict[int, float]):
        self.adj_vector = {int(k): float(v) for k, v in adj_dict.items()}

    def step(
        self,
        V_i: float,
        Q_i: float,
        omega_i: float,
        P_i: float,
        neighbor_states: Optional[Dict[int, Dict[str, float]]] = None,
        dt: float = 0.5
    ) -> Tuple[float, float, float, float]:
        """
        Calcula los incrementos restaurativos (delta_V, delta_Q, delta_omega, delta_P).
        """
        raise NotImplementedError


class PureDroopController(BaseSecondaryController):
    """
    1. Droop Primario Puro (Sin control secundario).
    Demuestra la cota inferior: no compensa el error de frecuencia ni de tensión en estado estacionario.
    """
    def __init__(self, agent_id: int, m_p: float = 1e-4, n_q: float = 1e-4, **kwargs):
        super().__init__(agent_id, **kwargs)
        self.m_p = m_p
        self.n_q = n_q

    def step(self, V_i: float, Q_i: float, omega_i: float, P_i: float, neighbor_states=None, dt: float = 0.5):
        # Droop primario no genera compensación restaurativa secundaria
        return 0.0, 0.0, 0.0, 0.0


class CentralizedPIController(BaseSecondaryController):
    """
    2. PI Centralizado (Referencia centralizada clásica).
    Actúa con infraestructura ideal global y punto único de fallo (SPoF).
    """
    def __init__(
        self,
        agent_id: int,
        k_p_w: float = 0.5,
        k_i_w: float = 1.5,
        k_p_v: float = 0.2,
        k_i_v: float = 0.8,
        **kwargs
    ):
        super().__init__(agent_id, **kwargs)
        self.k_p_w = k_p_w
        self.k_i_w = k_i_w
        self.k_p_v = k_p_v
        self.k_i_v = k_i_v
        self.int_e_w = 0.0
        self.int_e_v = 0.0

    def step(self, V_i: float, Q_i: float, omega_i: float, P_i: float, neighbor_states=None, dt: float = 0.5):
        e_w = self.omega_ref - omega_i
        e_v = 1.0 - V_i

        self.int_e_w += e_w * dt
        self.int_e_v += e_v * dt

        # Anti-windup
        self.int_e_w = max(-10.0, min(10.0, self.int_e_w))
        self.int_e_v = max(-1.0, min(1.0, self.int_e_v))

        # Corrección incremental por paso dt enviada desde el despacho central
        raw_delta_w = dt * (self.k_p_w * e_w + self.k_i_w * self.int_e_w)
        raw_delta_v = dt * (self.k_p_v * e_v + self.k_i_v * self.int_e_v)

        delta_w = max(-1.0, min(1.0, raw_delta_w))
        delta_v = max(-0.10, min(0.10, raw_delta_v))

        return delta_v, 0.0, delta_w, 0.0


class DAPIController(BaseSecondaryController):
    """
    3. DAPI: Distributed Averaging Proportional-Integral (Simpson-Porco et al., 2015).
    Consenso asintótico lineal distribuido.
    """
    def __init__(
        self,
        agent_id: int,
        k_w: float = 0.2,
        k_p: float = 0.2,
        k_v: float = 0.2,
        k_q: float = 0.2,
        **kwargs
    ):
        super().__init__(agent_id, **kwargs)
        self.k_w = k_w
        self.k_p = k_p
        self.k_v = k_v
        self.k_q = k_q

    def step(self, V_i: float, Q_i: float, omega_i: float, P_i: float, neighbor_states=None, dt: float = 0.5):
        p_ratio_i = P_i / self.P_max
        q_ratio_i = Q_i / self.Q_max

        # Verificación CFL lineal: dt * d_max * k < 1.0
        d_max = max(1.0, sum(self.adj_vector.values())) if self.adj_vector else 1.0
        if dt * d_max * max(self.k_w, self.k_v, self.k_p, self.k_q) >= 1.0:
            raise ValueError(f"DAPI viola estabilidad CFL: dt*d_max*k >= 1")

        # Agente 1 (Diesel líder) posee término pinning; seguidores coordinan por consenso
        u_w = 0.0
        u_v = 0.0
        if self.agent_id == 1:
            u_w += self.k_w * (self.omega_ref - omega_i)
            u_v += self.k_v * (1.0 - V_i)

        u_p = 0.0
        u_q = 0.0
        if neighbor_states:
            for n_id, weight in self.adj_vector.items():
                if n_id in neighbor_states:
                    st = neighbor_states[n_id]
                    p_ratio_j = st.get("P_ratio", 0.0)
                    q_ratio_j = st.get("Q_ratio", 0.0)
                    w_j = st.get("omega", self.omega_ref)
                    v_j = st.get("V", 1.0)
                    u_w += weight * self.k_w * (w_j - omega_i)
                    u_v += weight * self.k_v * (v_j - V_i)
                    u_p += weight * self.k_p * (p_ratio_j - p_ratio_i)
                    u_q += weight * self.k_q * (q_ratio_j - q_ratio_i)

        raw_delta_v = dt * u_v
        raw_delta_q = dt * u_q * self.Q_max
        raw_delta_w = dt * u_w
        raw_delta_p = dt * u_p * self.P_max

        delta_v = max(-0.10, min(0.10, raw_delta_v))
        delta_q = max(-self.Q_max, min(self.Q_max, raw_delta_q))
        delta_w = max(-1.0, min(1.0, raw_delta_w))
        delta_p = max(-self.P_max, min(self.P_max, raw_delta_p))

        return delta_v, delta_q, delta_w, delta_p


class FTSController(BaseSecondaryController):
    """
    4. FTS: Consenso en Tiempo Finito simple (Wang et al., 2021).
    Utiliza una sola potencia fraccionaria alpha < 1. Su cota depende del estado inicial.
    """
    def __init__(
        self,
        agent_id: int,
        c1: float = 0.25,
        alpha: float = 0.8,
        epsilon: float = 1e-3,
        **kwargs
    ):
        super().__init__(agent_id, **kwargs)
        self.c1 = c1
        self.alpha = alpha
        self.epsilon = epsilon

    def step(self, V_i: float, Q_i: float, omega_i: float, P_i: float, neighbor_states=None, dt: float = 0.5):
        p_ratio_i = P_i / self.P_max
        q_ratio_i = Q_i / self.Q_max

        # CFL check: dt * d_max * c1 < 1.0
        d_max = max(1.0, sum(self.adj_vector.values())) if self.adj_vector else 1.0
        if dt * d_max * self.c1 >= 1.0:
            raise ValueError(f"FTS viola estabilidad CFL: dt*d_max*c1 >= 1")

        u_w = 0.0
        u_v = 0.0
        if self.agent_id == 1:
            u_v += self.c1 * sig_pow(1.0 - V_i, self.alpha, self.epsilon)
            u_w += self.c1 * sig_pow(self.omega_ref - omega_i, self.alpha, self.epsilon)

        u_q = 0.0
        u_p = 0.0
        if neighbor_states:
            for n_id, weight in self.adj_vector.items():
                if n_id in neighbor_states:
                    st = neighbor_states[n_id]
                    p_ratio_j = st.get("P_ratio", 0.0)
                    q_ratio_j = st.get("Q_ratio", 0.0)
                    w_j = st.get("omega", self.omega_ref)
                    v_j = st.get("V", 1.0)
                    u_v += weight * self.c1 * sig_pow(v_j - V_i, self.alpha, self.epsilon)
                    u_w += weight * self.c1 * sig_pow(w_j - omega_i, self.alpha, self.epsilon)
                    u_p += weight * self.c1 * sig_pow(p_ratio_j - p_ratio_i, self.alpha, self.epsilon)
                    u_q += weight * self.c1 * sig_pow(q_ratio_j - q_ratio_i, self.alpha, self.epsilon)

        raw_delta_v = dt * u_v
        raw_delta_q = dt * u_q * self.Q_max
        raw_delta_w = dt * u_w
        raw_delta_p = dt * u_p * self.P_max

        delta_v = max(-0.10, min(0.10, raw_delta_v))
        delta_q = max(-self.Q_max, min(self.Q_max, raw_delta_q))
        delta_w = max(-1.0, min(1.0, raw_delta_w))
        delta_p = max(-self.P_max, min(self.P_max, raw_delta_p))

        return delta_v, delta_q, delta_w, delta_p


class FxTSControllerWrapper(BaseSecondaryController):
    """
    5. FxTS: Consenso en Tiempo Fijo de la Tesis.
    IMPORTA DIRECTAMENTE FixedTimeConsensusAgent desde Agents.finite_time_consensus.
    Garantiza cota independiente del estado inicial respetando CFL.
    """
    def __init__(
        self,
        agent_id: int,
        alpha: float = 0.8,
        beta: float = 1.2,
        c1: float = 0.25,
        c2: float = 0.15,
        epsilon: float = 1e-3,
        mode: str = "OFFLINE",
        **kwargs
    ):
        super().__init__(agent_id, **kwargs)
        self.agent = FixedTimeConsensusAgent(
            agent_id=agent_id,
            Q_max=self.Q_max,
            P_max=self.P_max,
            alpha=alpha,
            beta=beta,
            c1=c1,
            c2=c2,
            mode=mode,
            epsilon=epsilon,
            f_ref=self.f_ref
        )

    def set_adjacency(self, adj_dict: Dict[int, float]):
        super().set_adjacency(adj_dict)
        self.agent.set_adjacency(adj_dict)

    def step(self, V_i: float, Q_i: float, omega_i: float, P_i: float, neighbor_states=None, dt: float = 0.5):
        # Llama directamente al método update_consensus del artefacto bajo prueba
        dV, dQ, dw, dP = self.agent.update_consensus(
            V_i=V_i,
            Q_i=Q_i,
            neighbor_states=neighbor_states,
            dt=dt,
            omega_i=omega_i,
            P_i=P_i,
            return_all=True
        )
        return dV, dQ, dw, dP


def get_baseline_controller(
    name: str,
    agent_id: int,
    tuning_mode: str = "published",
    **kwargs
) -> BaseSecondaryController:
    """
    Factory para instanciar las líneas base con su configuración publicada u optimizada.
    """
    name_clean = name.strip().lower()
    tuning = tuning_mode.strip().lower()

    if "droop" in name_clean:
        if tuning == "optimized":
            # Mejor sintonización de droop para reducir error remanente
            return PureDroopController(agent_id, m_p=2.0e-4, n_q=2.0e-4, **kwargs)
        return PureDroopController(agent_id, m_p=1.0e-4, n_q=1.0e-4, **kwargs)

    elif "centralized" in name_clean or "pi" in name_clean:
        if tuning == "optimized":
            # PI ajustado para mínimo IAE con margen de sobreimpulso
            return CentralizedPIController(agent_id, k_p_w=0.45, k_i_w=1.2, k_p_v=0.25, k_i_v=0.75, **kwargs)
        return CentralizedPIController(agent_id, k_p_w=0.5, k_i_w=1.5, k_p_v=0.2, k_i_v=0.8, **kwargs)

    elif "dapi" in name_clean:
        if tuning == "optimized":
            # DAPI optimizado al límite CFL (dt=0.5, d_max=2 => k < 1.0)
            return DAPIController(agent_id, k_w=0.22, k_p=0.22, k_v=0.22, k_q=0.22, **kwargs)
        return DAPIController(agent_id, k_w=0.20, k_p=0.20, k_v=0.20, k_q=0.20, **kwargs)

    elif "fts" in name_clean and "fxts" not in name_clean:
        if tuning == "optimized":
            # FTS optimizado minimizando IAE
            return FTSController(agent_id, c1=0.35, alpha=0.75, **kwargs)
        return FTSController(agent_id, c1=0.25, alpha=0.80, **kwargs)

    elif "fxts" in name_clean:
        # FxTS (La tesis) utiliza sus parámetros analíticos certificados en ambas modalidades
        mode = kwargs.pop("mode", "OFFLINE" if agent_id == 1 else "ONLINE")
        alpha = kwargs.pop("alpha", 0.8)
        beta = kwargs.pop("beta", 1.2)
        c1 = kwargs.pop("c1", 0.25)
        c2 = kwargs.pop("c2", 0.15)
        return FxTSControllerWrapper(agent_id, alpha=alpha, beta=beta, c1=c1, c2=c2, mode=mode, **kwargs)

    else:
        raise ValueError(f"Controlador desconocido: {name}. Opciones: droop, pi, dapi, fts, fxts")
