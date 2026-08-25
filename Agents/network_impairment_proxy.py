import time
from typing import Any, Dict, List, Optional, Tuple
from common.network_channel_emulator import NetworkChannelEmulator

class NetworkImpairmentProxy:
    """
    Proxy y Gestor de Perturbaciones de Red para el Sistema Multi-Agente (MAS).
    
    Permite:
      - Interceptar el intercambio de estados entre agentes adyacentes (ZMQ / P2P).
      - Programar eventos dinámicos de red (ej. caídas de enlace, picos de latencia, ráfagas de pérdida).
      - Aplicar perfiles predefinidos de calidad de red (IDEAL, LAN_ETHERNET, INDUSTRIAL_WIFI, SEVERE_STRESS, CRITICAL_PARTITION).
    """

    PROFILES = {
        "IDEAL": {
            "base_latency_ms": 0.0,
            "jitter_ms": 0.0,
            "loss_rate": 0.0,
            "loss_model": "bernoulli",
            "noise_std": 0.0
        },
        "LAN_ETHERNET": {
            "base_latency_ms": 5.0,
            "jitter_ms": 2.0,
            "loss_rate": 0.005,
            "loss_model": "bernoulli",
            "noise_std": 1e-4
        },
        "INDUSTRIAL_WIFI": {
            "base_latency_ms": 30.0,
            "jitter_ms": 15.0,
            "loss_rate": 0.05,
            "loss_model": "bernoulli",
            "noise_std": 5e-4
        },
        "SEVERE_STRESS": {
            "base_latency_ms": 150.0,
            "jitter_ms": 60.0,
            "loss_rate": 0.20,
            "loss_model": "gilbert_elliott",
            "p_good_to_bad": 0.10,
            "p_bad_to_good": 0.40,
            "loss_in_bad": 0.90,
            "loss_in_good": 0.05,
            "noise_std": 1e-3
        },
        "CRITICAL_PARTITION": {
            "base_latency_ms": 250.0,
            "jitter_ms": 100.0,
            "loss_rate": 0.40,
            "loss_model": "bernoulli",
            "noise_std": 2e-3
        }
    }

    def __init__(self, profile: str = "IDEAL", custom_params: Optional[Dict[str, Any]] = None, seed: Optional[int] = None):
        self.profile_name = profile.upper()
        params = self.PROFILES.get(self.profile_name, self.PROFILES["IDEAL"]).copy()
        if custom_params:
            params.update(custom_params)

        self.emulator = NetworkChannelEmulator(**params, seed=seed)
        self.scheduled_events: List[Dict[str, Any]] = []

    def set_profile(self, profile: str):
        """Cambia el perfil de calidad del canal en caliente."""
        if profile.upper() in self.PROFILES:
            self.profile_name = profile.upper()
            params = self.PROFILES[self.profile_name]
            self.emulator.base_latency_ms = params["base_latency_ms"]
            self.emulator.jitter_ms = params["jitter_ms"]
            self.emulator.loss_rate = params["loss_rate"]
            self.emulator.loss_model = params.get("loss_model", "bernoulli")
            self.emulator.noise_std = params.get("noise_std", 0.0)

    def schedule_link_outage(self, u: int, v: int, start_step: int, duration_steps: int):
        """Programa el corte temporal de un enlace entre nodos u y v durante un número de pasos de simulación."""
        self.scheduled_events.append({
            "type": "LINK_OUTAGE",
            "u": u,
            "v": v,
            "start_step": start_step,
            "end_step": start_step + duration_steps
        })

    def process_step_events(self, current_step: int):
        """Aplica las contingencias programadas para el paso de simulación actual."""
        for event in self.scheduled_events:
            if event["type"] == "LINK_OUTAGE":
                u, v = event["u"], event["v"]
                if event["start_step"] <= current_step < event["end_step"]:
                    self.emulator.set_link_state(u, v, enabled=False)
                elif current_step >= event["end_step"]:
                    self.emulator.set_link_state(u, v, enabled=True)

    def filter_neighbor_states(
        self,
        receiver_id: int,
        raw_neighbor_states: Dict[int, Dict[str, float]],
        current_step: Optional[int] = None,
        current_time_s: Optional[float] = None
    ) -> Tuple[Dict[int, Dict[str, float]], Dict[str, Any]]:
        """
        Filtra y corrompe los estados vecinos recibidos por un agente según el estado del canal.

        Parámetros:
            receiver_id: ID del agente que recibe los datos.
            raw_neighbor_states: Dict {sender_id: {"V": V_j, "Q_ratio": Q_ratio_j, ...}}
            current_step: Paso actual para evaluar eventos programados.
            current_time_s: Timestamp actual para colas de retardo.

        Retorna:
            (filtered_states, telemetry_meta)
            filtered_states contendrá solo los vecinos cuyos paquetes fueron entregados con éxito (posiblemente con ruido).
        """
        if current_step is not None:
            self.process_step_events(current_step)

        filtered_states = {}
        delivery_meta = {
            "receiver_id": receiver_id,
            "attempted": len(raw_neighbor_states),
            "delivered": 0,
            "dropped": 0,
            "latencies_ms": {}
        }

        for sender_id, state in raw_neighbor_states.items():
            success, received_payload, latency_ms = self.emulator.transmit(
                sender_id=sender_id,
                receiver_id=receiver_id,
                payload=state,
                current_time_s=current_time_s
            )

            if success and received_payload is not None:
                filtered_states[sender_id] = received_payload
                delivery_meta["delivered"] += 1
                delivery_meta["latencies_ms"][sender_id] = latency_ms
            else:
                delivery_meta["dropped"] += 1

        return filtered_states, delivery_meta

    def get_network_health(self) -> Dict[str, Any]:
        """Retorna estadísticas consolidadas del canal y perfil activo."""
        stats = self.emulator.get_statistics()
        stats["active_profile"] = self.profile_name
        stats["disabled_links"] = list(self.emulator.disabled_links)
        return stats
