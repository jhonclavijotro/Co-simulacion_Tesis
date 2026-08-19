import json
import time
import os

try:
    from influxdb_client import InfluxDBClient, Point
    from influxdb_client.client.write_api import SYNCHRONOUS
    INFLUX_AVAILABLE = True
except ImportError:
    INFLUX_AVAILABLE = False

class InfluxTelemetryLogger:
    """
    Gestor de Telemetría e Ingesta de Series Temporales en InfluxDB.
    Discretización: 500 ms.
    Registra: Tensiones |V_i|, Potencia Activa P_i, Potencia Reactiva Q_i y Modo Operativo.
    """
    def __init__(self, url="http://localhost:8086", token="my-token", org="my-org", bucket="microgrid_telemetry"):
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.connected = False
        self.local_log = []  # Fallback de almacenamiento local en memoria

        if INFLUX_AVAILABLE:
            try:
                self.client = InfluxDBClient(url=url, token=token, org=org)
                self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
                self.connected = True
            except Exception:
                self.client = None
                self.write_api = None
        else:
            self.client = None
            self.write_api = None

    def log_step(self, step_idx, mode, voltages, power_injections):
        """
        Registra un paso de simulación.
        
        Parámetros:
            step_idx: Int
            mode: String ("ONLINE" / "OFFLINE")
            voltages: Dict {node_id: {"V_pu": float, "V_volts": float}}
            power_injections: Dict {node_id: {"P": float, "Q": float}}
        """
        timestamp = time.time()
        record = {
            "step": step_idx,
            "timestamp": timestamp,
            "mode": mode,
            "voltages": voltages,
            "power_injections": power_injections
        }
        self.local_log.append(record)

        if self.connected and self.write_api:
            try:
                points = []
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
                self.write_api.write(bucket=self.bucket, org=self.org, record=points)
            except Exception as e:
                # Log local fallback silencioso
                pass

        return record

    def close(self):
        if self.client:
            self.client.close()

if __name__ == "__main__":
    logger = InfluxTelemetryLogger()
    v_sample = {1: {"V_pu": 1.0, "V_volts": 400.0}, 2: {"V_pu": 1.001, "V_volts": 400.4}}
    p_sample = {1: {"P": 5000.0, "Q": 1000.0}, 2: {"P": 8000.0, "Q": 2000.0}}
    rec = logger.log_step(1, "ONLINE", v_sample, p_sample)
    print("Registro Telemetría InfluxDB/Local:")
    print(json.dumps(rec, indent=2))
    logger.close()
