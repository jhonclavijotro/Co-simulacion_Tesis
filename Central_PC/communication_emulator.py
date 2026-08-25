"""
Módulo de Emulación de Imperfecciones del Canal de Comunicación.

Emula las condiciones reales de una red de comunicación distribuida (latencia,
jitter, pérdida de paquetes) sobre el canal ZeroMQ que actualmente corre
en localhost con latencia de microsegundos.

Escenarios Predefinidos:
  - IDEAL:           Sin retardo ni pérdida (baseline de referencia).
  - LOW_DELAY:       Retardo uniforme [50, 100] ms, 0% pérdida.
  - HIGH_DELAY:      Retardo uniforme [200, 350] ms, 0% pérdida.
  - PACKET_LOSS_5PCT: Retardo uniforme [20, 80] ms, 5% pérdida de paquetes.
  - SEVERE:          Retardo uniforme [150, 400] ms, 10% pérdida de paquetes.

Uso:
  emulator = CommunicationEmulator(scenario="LOW_DELAY")
  emulator.apply_delay()                        # Introduce retardo antes de enviar
  filtered = emulator.filter_injections(inj)    # Descarta nodos según drop_rate

Justificación Académica:
  El Objetivo 1 de la tesis exige demostrar estabilidad del algoritmo de consenso
  bajo "comunicaciones imperfectas". Sin esta emulación, la validación del objetivo
  queda vacía dado que el canal ZMQ local tiene latencia de ~μs y 0% pérdida.
"""

import time
import random
import copy


# Escenarios predefinidos de emulación de red
SCENARIOS = {
    "IDEAL": {
        "tau_min": 0.0,       # Retardo mínimo [s]
        "tau_max": 0.0,       # Retardo máximo [s]
        "drop_rate": 0.0,     # Probabilidad de pérdida de paquete [0..1]
        "description": "Canal ideal: sin retardo ni pérdida (baseline)."
    },
    "LOW_DELAY": {
        "tau_min": 0.050,     # 50 ms
        "tau_max": 0.100,     # 100 ms
        "drop_rate": 0.0,
        "description": "Retardo bajo (50-100 ms), sin pérdida. Red LAN/Ethernet local."
    },
    "HIGH_DELAY": {
        "tau_min": 0.200,     # 200 ms
        "tau_max": 0.350,     # 350 ms
        "drop_rate": 0.0,
        "description": "Retardo alto (200-350 ms), sin pérdida. Red WiFi congestionada."
    },
    "PACKET_LOSS_5PCT": {
        "tau_min": 0.020,     # 20 ms
        "tau_max": 0.080,     # 80 ms
        "drop_rate": 0.05,    # 5%
        "description": "Retardo moderado (20-80 ms) con 5% pérdida de paquetes."
    },
    "SEVERE": {
        "tau_min": 0.150,     # 150 ms
        "tau_max": 0.400,     # 400 ms
        "drop_rate": 0.10,    # 10%
        "description": "Condiciones severas: retardo alto (150-400 ms) con 10% pérdida."
    },
}


class CommunicationEmulator:
    """
    Emulador de imperfecciones del canal de comunicación para co-simulación HIL.

    Introduce retardo variable (jitter) y pérdida de paquetes sobre las
    inyecciones de potencia recolectadas en cada paso del reloj maestro,
    simulando las condiciones reales de una red de comunicación distribuida.

    Atributos:
        scenario:    Nombre del escenario activo (str).
        tau_min:     Retardo mínimo en segundos (float).
        tau_max:     Retardo máximo en segundos (float).
        drop_rate:   Probabilidad de pérdida de paquete por nodo [0..1] (float).
        stats:       Diccionario con contadores de diagnóstico.
    """

    def __init__(self, scenario="IDEAL", seed=None):
        """
        Inicializa el emulador con un escenario predefinido o parámetros custom.

        Parámetros:
            scenario:  Nombre del escenario predefinido (str) o dict con
                       claves {tau_min, tau_max, drop_rate}.
            seed:      Semilla para reproducibilidad de las perturbaciones (int|None).
        """
        if isinstance(scenario, dict):
            self.scenario = "CUSTOM"
            self.tau_min = scenario.get("tau_min", 0.0)
            self.tau_max = scenario.get("tau_max", 0.0)
            self.drop_rate = scenario.get("drop_rate", 0.0)
        elif scenario.upper() in SCENARIOS:
            self.scenario = scenario.upper()
            cfg = SCENARIOS[self.scenario]
            self.tau_min = cfg["tau_min"]
            self.tau_max = cfg["tau_max"]
            self.drop_rate = cfg["drop_rate"]
        else:
            raise ValueError(
                f"Escenario desconocido: '{scenario}'. "
                f"Opciones válidas: {list(SCENARIOS.keys())} o un dict custom."
            )

        self._rng = random.Random(seed)
        self.stats = {
            "total_steps": 0,
            "total_nodes_processed": 0,
            "total_nodes_dropped": 0,
            "total_delay_applied_s": 0.0,
        }

    def apply_delay(self):
        """
        Introduce un retardo aleatorio uniforme en [tau_min, tau_max].

        Este método debe invocarse antes de procesar las inyecciones de un paso
        de co-simulación para emular la latencia de red.

        Retorna:
            float: El retardo efectivamente aplicado en segundos.
        """
        if self.tau_max <= 0:
            return 0.0

        delay = self._rng.uniform(self.tau_min, self.tau_max)
        time.sleep(delay)
        self.stats["total_delay_applied_s"] += delay
        return delay

    def filter_injections(self, node_injections):
        """
        Filtra las inyecciones de nodo simulando pérdida de paquetes.

        Cada nodo tiene una probabilidad independiente `drop_rate` de que
        su inyección sea descartada en el paso actual, emulando la pérdida
        de un mensaje en el canal de comunicación.

        Parámetros:
            node_injections: Dict {node_id: {"P": watts, "Q": vars}}

        Retorna:
            Dict filtrado (copia profunda) con los nodos que "sobrevivieron"
            la transmisión. Los nodos descartados no aparecen en el resultado.
        """
        self.stats["total_steps"] += 1

        if self.drop_rate <= 0:
            self.stats["total_nodes_processed"] += len(node_injections)
            return copy.deepcopy(node_injections)

        filtered = {}
        for node_id, data in node_injections.items():
            self.stats["total_nodes_processed"] += 1
            if self._rng.random() < self.drop_rate:
                self.stats["total_nodes_dropped"] += 1
                continue  # Paquete perdido
            filtered[node_id] = copy.deepcopy(data)

        return filtered

    def get_stats(self):
        """Retorna el diccionario de estadísticas de diagnóstico."""
        stats = dict(self.stats)
        if stats["total_nodes_processed"] > 0:
            stats["effective_drop_rate"] = round(
                stats["total_nodes_dropped"] / stats["total_nodes_processed"], 4
            )
        else:
            stats["effective_drop_rate"] = 0.0
        return stats

    def get_scenario_description(self):
        """Retorna la descripción del escenario activo."""
        if self.scenario in SCENARIOS:
            return SCENARIOS[self.scenario]["description"]
        return (f"Custom: tau=[{self.tau_min*1000:.0f}, {self.tau_max*1000:.0f}] ms, "
                f"drop={self.drop_rate*100:.1f}%")

    def __repr__(self):
        return (f"CommunicationEmulator(scenario='{self.scenario}', "
                f"tau=[{self.tau_min*1000:.0f}-{self.tau_max*1000:.0f}]ms, "
                f"drop_rate={self.drop_rate*100:.1f}%)")
