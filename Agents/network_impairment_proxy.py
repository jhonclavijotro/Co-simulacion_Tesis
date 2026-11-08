import csv
import hashlib
import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple
from common.network_channel_emulator import NetworkChannelEmulator

class NetworkImpairmentProxy:
    """
    Proxy y Gestor de Perturbaciones de Red para el Sistema Multi-Agente (MAS).
    
    Implementa el contrato normativo D-25 de contingencias telemáticas (Anexo O-10)
    y perturbaciones ciberfísicas para la evaluación de resiliencia (S-34 / Familia 3 D-24):
      - Interceptación y filtrado de estados de consenso P2P entre agentes adyacentes.
      - Soporte para perfiles predefinidos (IDEAL, LAN_ETHERNET, INDUSTRIAL_WIFI, SEVERE_STRESS, CRITICAL_PARTITION).
      - Ingesta de contingencias temporales desde archivo CSV normativo (14 columnas) o API programática.
      - Derivación determinista de semillas pseudoaleatorias por celda según D-25:
          semilla = sha256("{semilla_base}|{id}|{origen}|{destino}")[:8]
      - Modelado de latencia (50-500 ms con rampas lineales), pérdida estocástica de paquetes (0-30% Bernoulli),
        y corte/reconexión de enlaces dirigidos (desconexión).
      - Telemetría de entrega paso a paso (delivery_meta) con trazabilidad de contingencias activas.
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

    D25_COLUMNS = [
        "id", "tipo", "alcance", "origen", "destino", "inicio_s", "fin_s",
        "param_min", "param_max", "unidad", "modelo", "reintento_s", "semilla", "justificacion"
    ]

    def __init__(self, profile: str = "IDEAL", custom_params: Optional[Dict[str, Any]] = None, seed: Optional[int] = None):
        self.profile_name = profile.upper()
        self.base_seed = seed if seed is not None else 42
        params = self.PROFILES.get(self.profile_name, self.PROFILES["IDEAL"]).copy()
        if custom_params:
            params.update(custom_params)

        self.emulator = NetworkChannelEmulator(**params, seed=self.base_seed)
        self.scheduled_events: List[Dict[str, Any]] = []
        self.contingencies: List[Dict[str, Any]] = []
        self.contingency_prngs: Dict[str, random.Random] = {}
        self.link_overrides: Dict[Tuple[int, int], Dict[str, Any]] = {}
        self.step_history: List[Dict[str, Any]] = []

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

    def set_link_impairment(
        self,
        u: int,
        v: int,
        latency_ms: Optional[float] = None,
        loss_rate: Optional[float] = None,
        enabled: Optional[bool] = None
    ):
        """Define o actualiza parámetros de enlace específicos dirigidos u -> v."""
        key = (int(u), int(v))
        if key not in self.link_overrides:
            self.link_overrides[key] = {}
        if latency_ms is not None:
            self.link_overrides[key]["latency_ms"] = float(latency_ms)
        if loss_rate is not None:
            self.link_overrides[key]["loss_rate"] = float(loss_rate)
        if enabled is not None:
            self.link_overrides[key]["enabled"] = bool(enabled)
            self.emulator.set_link_state(u, v, enabled=bool(enabled))

    def load_contingencies_csv(self, csv_path: str, semilla_base: Optional[int] = None):
        """
        Carga contingencias telemáticas desde un archivo CSV conforme al contrato normativo D-25 (14 columnas).
        Deriva semillas deterministas por celda si la columna 'semilla' está vacía o no declarada.
        """
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Archivo de contingencias telemáticas no encontrado: {csv_path}")

        s_base = semilla_base if semilla_base is not None else self.base_seed

        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            # Validar existencia de columnas requeridas si hay cabecera
            if reader.fieldnames:
                for col in self.D25_COLUMNS:
                    if col not in reader.fieldnames:
                        raise ValueError(f"Columna requerida D-25 faltante en {csv_path}: '{col}'")

            for row in reader:
                c_id = row["id"].strip()
                if not c_id:
                    continue

                tipo = row["tipo"].strip().lower()
                alcance = row["alcance"].strip().lower()

                origen_str = row["origen"].strip()
                destino_str = row["destino"].strip()
                origen = int(origen_str) if origen_str else None
                destino = int(destino_str) if destino_str else None

                inicio_s = float(row["inicio_s"].strip())
                fin_s = float(row["fin_s"].strip())

                pmin_str = row.get("param_min", "").strip()
                pmax_str = row.get("param_max", "").strip()
                param_min = float(pmin_str) if pmin_str else None
                param_max = float(pmax_str) if pmax_str else None

                unidad = row.get("unidad", "").strip().lower()
                modelo = row.get("modelo", "").strip().lower()

                reintento_str = row.get("reintento_s", "").strip()
                reintento_s = float(reintento_str) if reintento_str else 5.0

                semilla_str = row.get("semilla", "").strip()
                if not semilla_str:
                    # Fórmula D-25 §4: sha256("{semilla_base}|{id}|{origen}|{destino}")[:8]
                    hash_key = f"{s_base}|{c_id}|{origen_str}|{destino_str}"
                    semilla_str = hashlib.sha256(hash_key.encode("utf-8")).hexdigest()[:8]

                justificacion = row.get("justificacion", "").strip()

                self.add_contingency(
                    c_id=c_id,
                    tipo=tipo,
                    alcance=alcance,
                    origen=origen,
                    destino=destino,
                    inicio_s=inicio_s,
                    fin_s=fin_s,
                    param_min=param_min,
                    param_max=param_max,
                    unidad=unidad,
                    modelo=modelo,
                    reintento_s=reintento_s,
                    semilla=semilla_str,
                    justificacion=justificacion
                )

    def add_contingency(
        self,
        c_id: str,
        tipo: str,
        alcance: str,
        origen: Optional[int] = None,
        destino: Optional[int] = None,
        inicio_s: float = 0.0,
        fin_s: float = 0.0,
        param_min: Optional[float] = None,
        param_max: Optional[float] = None,
        unidad: str = "",
        modelo: str = "bernoulli",
        reintento_s: float = 5.0,
        semilla: Optional[str] = None,
        justificacion: str = ""
    ):
        """Agrega programáticamente una contingencia telemática con su propio PRNG aislado."""
        if not semilla:
            orig_s = str(origen) if origen is not None else ""
            dest_s = str(destino) if destino is not None else ""
            hash_key = f"{self.base_seed}|{c_id}|{orig_s}|{dest_s}"
            semilla = hashlib.sha256(hash_key.encode("utf-8")).hexdigest()[:8]

        seed_int = int(semilla, 16)
        prng = random.Random(seed_int)
        prng_key = f"{c_id}_{origen}_{destino}"
        self.contingency_prngs[prng_key] = prng

        contingency = {
            "id": c_id,
            "tipo": tipo.lower(),
            "alcance": alcance.lower(),
            "origen": origen,
            "destino": destino,
            "inicio_s": float(inicio_s),
            "fin_s": float(fin_s),
            "param_min": float(param_min) if param_min is not None else None,
            "param_max": float(param_max) if param_max is not None else None,
            "unidad": unidad.lower(),
            "modelo": modelo.lower() if modelo else "bernoulli",
            "reintento_s": float(reintento_s),
            "semilla": semilla,
            "prng_key": prng_key,
            "justificacion": justificacion
        }
        self.contingencies.append(contingency)

    def schedule_link_outage(self, u: int, v: int, start_step: int, duration_steps: int):
        """Programa el corte temporal de un enlace entre nodos u y v durante un número de pasos de simulación (retrocompatibilidad)."""
        self.scheduled_events.append({
            "type": "LINK_OUTAGE",
            "u": int(u),
            "v": int(v),
            "start_step": int(start_step),
            "end_step": int(start_step + duration_steps)
        })

    def process_step_events(self, current_step: int):
        """Aplica las contingencias por paso programadas para el paso de simulación actual."""
        for event in self.scheduled_events:
            if event["type"] == "LINK_OUTAGE":
                u, v = event["u"], event["v"]
                if event["start_step"] <= current_step < event["end_step"]:
                    self.emulator.set_link_state(u, v, enabled=False)
                elif current_step >= event["end_step"]:
                    self.emulator.set_link_state(u, v, enabled=True)

    def get_active_contingencies(self, current_time_s: float) -> List[Dict[str, Any]]:
        """Retorna la lista de contingencias D-25 activas en el instante temporal dado [s]."""
        active = []
        for c in self.contingencies:
            if c["inicio_s"] <= current_time_s < c["fin_s"]:
                active.append(c)
        return active

    def filter_neighbor_states(
        self,
        receiver_id: int,
        raw_neighbor_states: Dict[int, Dict[str, float]],
        current_step: Optional[int] = None,
        current_time_s: Optional[float] = None
    ) -> Tuple[Dict[int, Dict[str, float]], Dict[str, Any]]:
        """
        Filtra y perturba los estados vecinos recibidos por un agente según el estado del canal
        y las contingencias activas (D-25 / S-34).

        Parámetros:
            receiver_id: ID del agente que recibe los datos.
            raw_neighbor_states: Dict {sender_id: {"V": V_j, "Q_ratio": Q_ratio_j, ...}}
            current_step: Paso actual para evaluar eventos programados.
            current_time_s: Timestamp continuo actual [s]. Si no se provee, se calcula como current_step * 0.5.

        Retorna:
            (filtered_states, delivery_meta)
            filtered_states contendrá solo los vecinos cuyos paquetes fueron entregados con éxito.
        """
        if current_step is not None:
            self.process_step_events(current_step)

        if current_time_s is None:
            current_time_s = float(current_step * 0.5) if current_step is not None else 0.0

        active_conts = self.get_active_contingencies(current_time_s)

        filtered_states = {}
        latencies: Dict[int, float] = {}
        dropped_count = 0

        for sender_id, state in raw_neighbor_states.items():
            sender_id = int(sender_id)
            link_key = (sender_id, int(receiver_id))

            # 1. Comprobar si el enlace está desconectado físicamente o por emulador
            is_disconnected = False
            if link_key in self.emulator.disabled_links:
                is_disconnected = True

            # Comprobar overrides estáticos de enlace
            if link_key in self.link_overrides and not self.link_overrides[link_key].get("enabled", True):
                is_disconnected = True

            # Filtrar contingencias activas aplicables a este canal dirigido (sender -> receiver)
            link_conts = [
                c for c in active_conts
                if c["alcance"] == "global" or (
                    c["alcance"] == "enlace" and c["origen"] == sender_id and c["destino"] == int(receiver_id)
                )
            ]

            # Evaluar contingencia de desconexión
            for c in link_conts:
                if c["tipo"] == "desconexion":
                    is_disconnected = True
                    break

            if is_disconnected:
                dropped_count += 1
                continue

            # 2. Comprobar pérdida de paquete (Bernoulli o Gilbert-Elliott)
            is_lost = False
            loss_conts = [c for c in link_conts if c["tipo"] == "perdida"]
            if loss_conts:
                # Tomar la primera contingencia de pérdida activa (conforme a R-L.2 sin solape sobre misma clave)
                c_loss = loss_conts[0]
                p_min = c_loss["param_min"] if c_loss["param_min"] is not None else 0.0
                p_max = c_loss["param_max"] if c_loss["param_max"] is not None else p_min
                dur = max(1e-6, c_loss["fin_s"] - c_loss["inicio_s"])
                frac = max(0.0, min(1.0, (current_time_s - c_loss["inicio_s"]) / dur))
                p_loss = p_min + frac * (p_max - p_min)

                prng = self.contingency_prngs.get(c_loss["prng_key"], random)
                if prng.random() < p_loss:
                    is_lost = True
            elif link_key in self.link_overrides and "loss_rate" in self.link_overrides[link_key]:
                override_rate = self.link_overrides[link_key]["loss_rate"]
                if random.random() < override_rate:
                    is_lost = True
            else:
                # Pérdida de línea base del emulador
                if self.emulator._is_packet_lost():
                    is_lost = True

            if is_lost:
                dropped_count += 1
                continue

            # 3. Calcular latencia de entrega (ms)
            lat_conts = [c for c in link_conts if c["tipo"] == "latencia"]
            if lat_conts:
                c_lat = lat_conts[0]
                l_min = c_lat["param_min"] if c_lat["param_min"] is not None else self.emulator.base_latency_ms
                l_max = c_lat["param_max"] if c_lat["param_max"] is not None else l_min
                dur = max(1e-6, c_lat["fin_s"] - c_lat["inicio_s"])
                frac = max(0.0, min(1.0, (current_time_s - c_lat["inicio_s"]) / dur))
                base_lat = l_min + frac * (l_max - l_min)

                prng = self.contingency_prngs.get(c_lat["prng_key"], random)
                if self.emulator.jitter_ms > 0:
                    lat_sample = max(0.0, prng.gauss(base_lat, self.emulator.jitter_ms))
                else:
                    lat_sample = max(0.0, base_lat)
            elif link_key in self.link_overrides and "latency_ms" in self.link_overrides[link_key]:
                base_lat = self.link_overrides[link_key]["latency_ms"]
                if self.emulator.jitter_ms > 0:
                    lat_sample = max(0.0, random.gauss(base_lat, self.emulator.jitter_ms))
                else:
                    lat_sample = max(0.0, base_lat)
            else:
                lat_sample = self.emulator._sample_latency()

            # 4. Inyección de ruido de medición y entrega exitosa
            noisy_payload = self.emulator._apply_noise(state)
            filtered_states[sender_id] = noisy_payload
            latencies[sender_id] = round(lat_sample, 2)

        lat_vals = list(latencies.values())
        avg_lat = round(sum(lat_vals) / len(lat_vals), 2) if lat_vals else 0.0
        total_attempted = len(raw_neighbor_states)
        drop_rate = round(dropped_count / total_attempted, 4) if total_attempted > 0 else 0.0

        delivery_meta = {
            "receiver_id": receiver_id,
            "step": current_step,
            "time_s": round(current_time_s, 4),
            "attempted": total_attempted,
            "delivered": len(filtered_states),
            "dropped": dropped_count,
            "latencies_ms": latencies,
            "latencias_ms": latencies,
            "active_contingencies": [c["id"] for c in active_conts],
            "falla_activa": len(active_conts) > 0,
            "latencia_efectiva_ms": avg_lat,
            "perdida_efectiva": drop_rate
        }

        self.step_history.append(delivery_meta)
        return filtered_states, delivery_meta

    def get_network_health(self) -> Dict[str, Any]:
        """Retorna estadísticas consolidadas del canal y perfil activo."""
        stats = self.emulator.get_statistics()
        stats["active_profile"] = self.profile_name
        stats["disabled_links"] = list(self.emulator.disabled_links)
        stats["contingencies_count"] = len(self.contingencies)
        stats["link_overrides"] = {f"{u}->{v}": cfg for (u, v), cfg in self.link_overrides.items()}
        return stats
