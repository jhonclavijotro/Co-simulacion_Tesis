import json
import time
import os
import csv
from typing import Optional, Dict, Any, List

try:
    from influxdb_client import InfluxDBClient, Point
    from influxdb_client.client.write_api import SYNCHRONOUS
    INFLUX_AVAILABLE = True
except ImportError:
    INFLUX_AVAILABLE = False

class InfluxTelemetryLogger:
    """
    Gestor de Telemetría e Ingesta de Series Temporales en InfluxDB y Almacenamiento Offline.
    Discretización: 500 ms (2 Hz).
    Registra:
      - Métricas eléctricas: Tensiones |V_i| (V y p.u.), Potencia Activa P_i (W), Potencia Reactiva Q_i (VAR) y Modo Operativo.
      - Métricas ciberfísicas de red: Latencia promedio (ms), Jitter, Ratio de pérdida de paquetes, Retardo acumulado.
      - Exportación persistente offline a disco en formatos CSV y JSON sin requerir InfluxDB.
    """
    def __init__(self, url="http://localhost:8086", token="my-token", org="my-org", bucket="microgrid_telemetry"):
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.connected = False
        self.local_log: List[Dict[str, Any]] = []  # Fallback y buffer de almacenamiento local en memoria

        if INFLUX_AVAILABLE:
            try:
                self.client = InfluxDBClient(url=url, token=token, org=org, timeout=1000)
                self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
                self.connected = True
            except Exception:
                self.client = None
                self.write_api = None
        else:
            self.client = None
            self.write_api = None

    def log_step(
        self,
        step_idx: int,
        mode: str,
        voltages: Dict[Any, Dict[str, float]],
        power_injections: Dict[Any, Dict[str, float]],
        network_stats: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Registra un paso de simulación en memoria y en InfluxDB si está disponible.
        
        Parámetros:
            step_idx: Número del paso de co-simulación.
            mode: String ("ONLINE" / "OFFLINE").
            voltages: Dict {node_id: {"V_pu": float, "V_volts": float}}.
            power_injections: Dict {node_id: {"P": float, "Q": float}}.
            network_stats: Dict con estadísticas de canal (latencia, pérdidas, jitter, etc.).
        """
        timestamp = time.time()
        record = {
            "step": step_idx,
            "timestamp": timestamp,
            "mode": mode,
            "voltages": voltages,
            "power_injections": power_injections,
            "network_stats": network_stats or {
                "profile": "IDEAL",
                "avg_delay_ms": 0.0,
                "packet_loss_ratio": 0.0,
                "total_sent": 0,
                "total_dropped": 0
            }
        }
        self.local_log.append(record)

        if self.connected and self.write_api:
            try:
                points = []
                # Puntos de telemetría de nodo
                for node_id, v_info in voltages.items():
                    p_info = power_injections.get(node_id, {"P": 0.0, "Q": 0.0})
                    point = Point("node_telemetry") \
                        .tag("node_id", str(node_id)) \
                        .tag("mode", mode) \
                        .field("V_pu", float(v_info.get("V_pu", 1.0))) \
                        .field("V_volts", float(v_info.get("V_volts", 400.0))) \
                        .field("P_w", float(p_info.get("P", 0.0))) \
                        .field("Q_var", float(p_info.get("Q", 0.0)))
                    points.append(point)
                
                # Punto de telemetría ciberfísica de canal
                if network_stats:
                    net_point = Point("network_telemetry") \
                        .tag("mode", mode) \
                        .tag("profile", str(network_stats.get("profile", "UNKNOWN"))) \
                        .field("avg_delay_ms", float(network_stats.get("avg_delay_ms", 0.0))) \
                        .field("packet_loss_ratio", float(network_stats.get("packet_loss_ratio", 0.0))) \
                        .field("total_sent", int(network_stats.get("total_sent", 0))) \
                        .field("total_dropped", int(network_stats.get("total_dropped", 0)))
                    points.append(net_point)

                self.write_api.write(bucket=self.bucket, org=self.org, record=points)
            except Exception:
                # Log local fallback silencioso
                pass

        return record

    def export_to_json(self, filepath: str) -> str:
        """Exporta el historial completo de la sesión actual a un archivo JSON."""
        abs_path = os.path.abspath(filepath)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            json.dump(self.local_log, f, indent=2)
        return abs_path

    def export_to_csv(self, filepath: str) -> str:
        """
        Exporta el historial en formato tabular plano CSV, ideal para análisis y graficación.
        Columnas: step, timestamp, mode, node_id, V_volts, V_pu, P_w, Q_var, net_latency_ms, net_loss_ratio.
        """
        abs_path = os.path.abspath(filepath)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        
        headers = [
            "step", "timestamp", "mode", "node_id",
            "V_volts", "V_pu", "P_w", "Q_var",
            "net_profile", "net_latency_ms", "net_loss_ratio"
        ]

        with open(abs_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

            for rec in self.local_log:
                step = rec.get("step", 0)
                ts = rec.get("timestamp", 0.0)
                mode = rec.get("mode", "ONLINE")
                voltages = rec.get("voltages", {})
                powers = rec.get("power_injections", {})
                net = rec.get("network_stats", {})
                net_profile = net.get("profile", "IDEAL")
                net_lat = net.get("avg_delay_ms", 0.0)
                net_loss = net.get("packet_loss_ratio", 0.0)

                for node_id, v_info in voltages.items():
                    p_info = powers.get(node_id, powers.get(str(node_id), {"P": 0.0, "Q": 0.0}))
                    writer.writerow([
                        step,
                        f"{ts:.4f}",
                        mode,
                        node_id,
                        f"{float(v_info.get('V_volts', 400.0)):.2f}",
                        f"{float(v_info.get('V_pu', 1.0)):.4f}",
                        f"{float(p_info.get('P', 0.0)):.2f}",
                        f"{float(p_info.get('Q', 0.0)):.2f}",
                        net_profile,
                        f"{net_lat:.2f}",
                        f"{net_loss:.4f}"
                    ])

        return abs_path

    def clear(self):
        """Limpia el buffer de registros en memoria para iniciar una nueva sesión."""
        self.local_log.clear()

    def close(self):
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass

if __name__ == "__main__":
    logger = InfluxTelemetryLogger()
    v_sample = {1: {"V_pu": 1.0, "V_volts": 400.0}, 2: {"V_pu": 1.001, "V_volts": 400.4}}
    p_sample = {1: {"P": 5000.0, "Q": 1000.0}, 2: {"P": 8000.0, "Q": 2000.0}}
    n_sample = {"profile": "INDUSTRIAL_WIFI", "avg_delay_ms": 35.2, "packet_loss_ratio": 0.05}
    rec = logger.log_step(1, "ONLINE", v_sample, p_sample, n_sample)
    print("Registro Telemetría InfluxDB/Local con Canal Ciberfísico:")
    print(json.dumps(rec, indent=2))
    
    out_csv = logger.export_to_csv("output_data/test_telemetry.csv")
    print(f"Exportación CSV exitosa en: {out_csv}")
    logger.close()
