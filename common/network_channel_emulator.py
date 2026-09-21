import random
import time
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

class NetworkChannelEmulator:
    """
    Emulador de Canal de Comunicación Ciberfísico para Sistemas Multi-Agente y Microrredes.
    
    Modela perturbaciones e imperfecciones reales en redes de comunicación (Ethernet, WiFi industrial, 4G/5G, ZigBee):
      1. Latencia y Jitter: Retardo base + variación estocástica (Normal / Uniforme).
      2. Pérdida de Paquetes:
         - Modelo Bernoulli: Pérdida aleatoria e independiente con probabilidad p_loss.
         - Modelo Gilbert-Elliott: Pérdida en ráfagas mediante cadena de Markov de 2 estados (GOOD, BAD).
      3. Ruido de Medición/Sensado: Inyección de ruido gaussiano N(0, sigma^2).
      4. Disrupciones Topológicas: Corte dinámico de enlaces (partición de grafos) por tiempo o pasos.
      5. Buffer FIFO con retardo para entrega de mensajes desfasados temporalmente.
    """

    def __init__(
        self,
        base_latency_ms: float = 0.0,
        jitter_ms: float = 0.0,
        loss_rate: float = 0.0,
        loss_model: str = "bernoulli",  # "bernoulli" o "gilbert_elliott"
        p_good_to_bad: float = 0.05,    # Transición G -> B en Gilbert-Elliott
        p_bad_to_good: float = 0.50,    # Transición B -> G en Gilbert-Elliott
        loss_in_bad: float = 0.95,      # Probabilidad de pérdida en estado BAD
        loss_in_good: float = 0.01,     # Probabilidad de pérdida en estado GOOD
        noise_std: float = 0.0,         # Desviación estándar de ruido en variables numéricas
        seed: Optional[int] = None
    ):
        if seed is not None:
            random.seed(seed)

        self.base_latency_ms = max(0.0, base_latency_ms)
        self.jitter_ms = max(0.0, jitter_ms)
        self.loss_rate = min(max(0.0, loss_rate), 1.0)
        self.loss_model = loss_model.lower()
        self.noise_std = max(0.0, noise_std)

        # Parámetros Gilbert-Elliott
        self.p_good_to_bad = p_good_to_bad
        self.p_bad_to_good = p_bad_to_good
        self.loss_in_bad = loss_in_bad
        self.loss_in_good = loss_in_good
        self.ge_state = "GOOD"

        # Enlaces deshabilitados dinámicamente: set de tuplas (from_node, to_node)
        self.disabled_links = set()

        # Cola de retardo para entrega asíncrona: lista de dicts con deliver_at_time
        self.in_flight_messages = deque()

        # Métricas estadísticas acumuladas
        self.total_transmitted = 0
        self.total_dropped = 0
        self.total_delivered = 0
        self.total_latency_accum_ms = 0.0

    def set_link_state(self, u: int, v: int, enabled: bool):
        """Habilita o deshabilita la comunicación direccional o bidireccional entre nodos u y v."""
        if enabled:
            self.disabled_links.discard((u, v))
            self.disabled_links.discard((v, u))
        else:
            self.disabled_links.add((u, v))
            self.disabled_links.add((v, u))

    def _sample_latency(self) -> float:
        """Genera una muestra de latencia estocástica en milisegundos."""
        if self.jitter_ms <= 0:
            return self.base_latency_ms
        # Jitter gaussiano truncado a >= 0
        sample = random.gauss(self.base_latency_ms, self.jitter_ms)
        return max(0.0, sample)

    def _is_packet_lost(self) -> bool:
        """Evalúa si el paquete actual se pierde según el modelo configurado."""
        if self.loss_model == "gilbert_elliott":
            # Transición de estado Markoviano
            if self.ge_state == "GOOD":
                if random.random() < self.p_good_to_bad:
                    self.ge_state = "BAD"
            else:
                if random.random() < self.p_bad_to_good:
                    self.ge_state = "GOOD"

            prob_loss = self.loss_in_bad if self.ge_state == "BAD" else self.loss_in_good
            return random.random() < prob_loss
        else:
            # Modelo Bernoulli simple e independiente
            return random.random() < self.loss_rate

    def _apply_noise(self, data: Any) -> Any:
        """Aplica ruido gaussiano a valores escalares o diccionarios numéricos."""
        if self.noise_std <= 0:
            return data
        if isinstance(data, (int, float)):
            return float(data) + random.gauss(0.0, self.noise_std)
        elif isinstance(data, dict):
            noisy_dict = {}
            for k, v in data.items():
                if isinstance(v, (int, float)):
                    noisy_dict[k] = float(v) + random.gauss(0.0, self.noise_std)
                elif isinstance(v, dict):
                    noisy_dict[k] = self._apply_noise(v)
                else:
                    noisy_dict[k] = v
            return noisy_dict
        return data

    def transmit(
        self,
        sender_id: int,
        receiver_id: int,
        payload: Any,
        current_time_s: Optional[float] = None
    ) -> Tuple[bool, Optional[Any], float]:
        """
        Simula la transmisión síncrona/inmediata de un mensaje a través del canal imperfecto.

        Retorna:
            (success: bool, received_payload: Optional[Any], latency_ms: float)
            - Si success=False (por pérdida o enlace cortado), received_payload es None.
        """
        self.total_transmitted += 1

        # 1. Verificar si el enlace está cortado
        if (sender_id, receiver_id) in self.disabled_links:
            self.total_dropped += 1
            return False, None, 0.0

        # 2. Evaluar pérdida estocástica
        if self._is_packet_lost():
            self.total_dropped += 1
            return False, None, 0.0

        # 3. Calcular latencia y aplicar ruido
        lat_ms = self._sample_latency()
        noisy_payload = self._apply_noise(payload)

        self.total_delivered += 1
        self.total_latency_accum_ms += lat_ms

        return True, noisy_payload, lat_ms

    def enqueue_message(
        self,
        sender_id: int,
        receiver_id: int,
        payload: Any,
        current_time_s: float
    ) -> bool:
        """
        Encola un mensaje con entrega asíncrona basada en tiempo (para reloj maestro o simuladores continuos).
        """
        self.total_transmitted += 1

        if (sender_id, receiver_id) in self.disabled_links or self._is_packet_lost():
            self.total_dropped += 1
            return False

        lat_ms = self._sample_latency()
        deliver_time = current_time_s + (lat_ms / 1000.0)
        noisy_payload = self._apply_noise(payload)

        self.in_flight_messages.append({
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "payload": noisy_payload,
            "deliver_at": deliver_time,
            "latency_ms": lat_ms
        })
        return True

    def receive_ready_messages(self, current_time_s: float) -> List[Dict[str, Any]]:
        """
        Extrae todos los mensajes cuya latencia ha expirado y están listos para entrega en current_time_s.
        """
        ready = []
        remaining = deque()

        while self.in_flight_messages:
            msg = self.in_flight_messages.popleft()
            if msg["deliver_at"] <= current_time_s:
                self.total_delivered += 1
                self.total_latency_accum_ms += msg["latency_ms"]
                ready.append(msg)
            else:
                remaining.append(msg)

        self.in_flight_messages = remaining
        return ready

    def get_statistics(self) -> Dict[str, float]:
        """Calcula métricas de desempeño de la red emulada."""
        drop_rate = (self.total_dropped / self.total_transmitted) if self.total_transmitted > 0 else 0.0
        avg_latency = (self.total_latency_accum_ms / self.total_delivered) if self.total_delivered > 0 else 0.0
        return {
            "total_transmitted": self.total_transmitted,
            "total_delivered": self.total_delivered,
            "total_dropped": self.total_dropped,
            "packet_loss_ratio": drop_rate,
            "average_latency_ms": avg_latency
        }

    def reset_statistics(self):
        """Reinicia los contadores de estadísticas de red."""
        self.total_transmitted = 0
        self.total_dropped = 0
        self.total_delivered = 0
        self.total_latency_accum_ms = 0.0
        self.in_flight_messages.clear()
