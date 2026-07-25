"""Logger de datos a InfluxDB via HTTP API.

Lee el historico del CoordinadorZMQ y lo escribe en InfluxDB 2.x
con discretizacion de 500 ms. Usa solo HTTP stdlib.
"""

import json
import time
import urllib.request
import urllib.error


class LoggerInflux:
    """Escribe time-series de la co-simulacion en InfluxDB OSS 2.x.

    Usa la HTTP API (/api/v2/write) con token de autenticacion.
    No requiere librerias externas.
    """

    def __init__(self, url="http://influxdb:8086", token="mas-token",
                 org="mas", bucket="simulacion"):
        self.url = url.rstrip("/")
        self.token = token
        self.org = org
        self.bucket = bucket
        self._buf = []

    def escribir(self, medicion, tags, fields, timestamp_ns=None):
        """Escribe un punto en formato Line Protocol."""
        ts = timestamp_ns or int(time.time() * 1e9)
        tags_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        fields_str = ",".join(
            f"{k}={v}" if isinstance(v, (int, float))
            else f'{k}="{v}"'
            for k, v in sorted(fields.items())
        )
        linea = f"{medicion},{tags_str} {fields_str} {ts}"
        self._buf.append(linea)

    def flush(self):
        """Envia todos los puntos acumulados a InfluxDB."""
        if not self._buf:
            return
        datos = "\n".join(self._buf).encode("utf-8")
        self._buf = []
        url = f"{self.url}/api/v2/write?org={self.org}&bucket={self.bucket}&precision=ns"
        req = urllib.request.Request(
            url, data=datos,
            headers={
                "Authorization": f"Token {self.token}",
                "Content-Type": "text/plain; charset=utf-8",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status != 204:
                    print(f"[LoggerInflux] Error HTTP {resp.status}: {resp.read()}")
        except (urllib.error.URLError, ConnectionRefusedError) as e:
            print(f"[LoggerInflux] Error conexion InfluxDB: {e}")

    def log_medicion(self, paso, tiempo, id_agente, SoC, P_ref, V_pcc=None):
        """Registra una medicion de agente."""
        self.escribir(
            medicion="medicion_agente",
            tags={"agente": f"agente_{id_agente}"},
            fields={
                "SoC": round(SoC, 6),
                "P_ref": round(P_ref, 1),
                "tiempo": round(tiempo, 3),
                "paso": paso,
            },
            timestamp_ns=int(tiempo * 1e9),
        )

    def log_coordinador(self, paso, tiempo, SoC_avg, demanda_w,
                         V_nodos=None):
        """Registra estado global del coordinador."""
        fields = {
            "SoC_avg": round(SoC_avg, 6),
            "demanda_w": round(demanda_w, 1),
            "tiempo": round(tiempo, 3),
            "paso": paso,
        }
        if V_nodos:
            for n, v in V_nodos.items():
                fields[f"V_{n}"] = round(v, 4)
        self.escribir(
            medicion="coordinador",
            tags={"tipo": "global"},
            fields=fields,
            timestamp_ns=int(tiempo * 1e9),
        )

    def log_meteo(self, tiempo, nodo, poa=None, temperatura=None,
                  viento=None, caudal=None):
        """Registra variable meteorologica."""
        fields = {"tiempo": round(tiempo, 3)}
        if poa is not None:
            fields["poa"] = round(poa, 1)
        if temperatura is not None:
            fields["temp"] = round(temperatura, 1)
        if viento is not None:
            fields["viento"] = round(viento, 2)
        if caudal is not None:
            fields["caudal"] = round(caudal, 3)
        self.escribir(
            medicion="meteorologia",
            tags={"nodo": str(nodo)},
            fields=fields,
            timestamp_ns=int(tiempo * 1e9),
        )
