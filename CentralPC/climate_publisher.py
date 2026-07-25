"""Publicador MQTT de variables meteorologicas.

Lee un archivo CSV con series temporales de irradiancia (POA),
temperatura, velocidad del viento, caudal, y las publica via MQTT
para que los nodos de generacion las consuman.

Requiere: paho-mqtt (pip install paho-mqtt)
"""

import csv
import json
import time
import threading


class ClimaPublisher:
    """Publica variables meteorologicas por MQTT con temporizacion real."""

    def __init__(self, archivo_csv, broker="mosquitto", puerto=1883,
                 intervalo=1.0, loop=False):
        self.archivo = archivo_csv
        self.broker = broker
        self.puerto = puerto
        self.intervalo = intervalo
        self.loop = loop
        self._datos = []
        self._indice = 0
        self._client = None
        self._thread = None
        self._running = False

    def _conectar(self):
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            print("[ClimaPublisher] paho-mqtt no instalado. "
                  "Usando mock local.")
            self._client = _MockMQTT()
            return
        self._client = mqtt.Client(client_id="clima-publisher")
        self._client.connect(self.broker, self.puerto, keepalive=60)
        self._client.loop_start()

    def _cargar_csv(self):
        self._datos = []
        try:
            with open(self.archivo, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    entry = {}
                    for k, v in row.items():
                        k = k.strip()
                        try:
                            entry[k] = float(v)
                        except ValueError:
                            entry[k] = v
                    self._datos.append(entry)
            print(f"[ClimaPublisher] Cargados {len(self._datos)} registros "
                  f"de {self.archivo}")
        except FileNotFoundError:
            print(f"[ClimaPublisher] {self.archivo} no encontrado. "
                  f"Generando datos sinteticos.")
            self._generar_sinteticos()

    def _generar_sinteticos(self, n=100):
        import random
        for i in range(n):
            t = i * self.intervalo
            self._datos.append({
                "tiempo": t,
                "poa": 600 + 200 * (1 - abs((t % 86400) / 43200 - 1)),
                "temperatura": 25 + 5 * (1 - abs((t % 86400) / 43200 - 1)),
                "viento": 5 + 3 * random.random(),
                "caudal": 2 + random.random(),
            })

    def _publicar(self, datos):
        topic_base = "mas/meteo"
        for key in ["poa", "temperatura", "viento", "caudal"]:
            if key in datos:
                topic = f"{topic_base}/{key}"
                payload = json.dumps({
                    "valor": datos[key],
                    "tiempo": datos.get("tiempo", time.time()),
                    "unidad": self._unidad(key),
                })
                self._client.publish(topic, payload, qos=1)

    @staticmethod
    def _unidad(key):
        unidades = {
            "poa": "W/m2",
            "temperatura": "C",
            "viento": "m/s",
            "caudal": "m3/s",
        }
        return unidades.get(key, "")

    def _loop(self):
        self._running = True
        while self._running and self._indice < len(self._datos):
            datos = self._datos[self._indice]
            self._publicar(datos)
            print(f"[ClimaPublisher] t={datos.get('tiempo', 0):.1f}s "
                  f"poa={datos.get('poa', 0):.0f} "
                  f"temp={datos.get('temperatura', 0):.1f}")
            self._indice += 1
            time.sleep(self.intervalo)
            if self._indice >= len(self._datos) and self.loop:
                self._indice = 0
        self._running = False
        print(f"[ClimaPublisher] Publicacion finalizada "
              f"({self._indice} registros)")

    def iniciar(self):
        self._conectar()
        self._cargar_csv()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def detener(self):
        self._running = False
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                pass


class _MockMQTT:
    """Mock para cuando paho-mqtt no esta disponible."""
    def publish(self, topic, payload, qos=1):
        print(f"  [MQTT MOCK] {topic}: {payload.decode()[:80] if isinstance(payload, bytes) else payload[:80]}...")
    def connect(self, *a, **kw):
        pass
    def loop_start(self):
        pass
    def disconnect(self):
        pass
