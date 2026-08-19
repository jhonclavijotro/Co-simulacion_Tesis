import json
import time
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mock_data.data_loader import MockDataLoader

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False

class MQTTPublisher:
    """
    Publicador MQTT para inyección de perfiles meteorológicos y demanda en tiempo real.
    Discretización: 500 ms (2 Hz).
    """
    def __init__(self, broker_host="localhost", broker_port=1883, client_id="Microgrid_Publisher"):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client_id = client_id
        self.data_loader = MockDataLoader()
        self.connected = False

        if MQTT_AVAILABLE:
            try:
                if hasattr(mqtt, "CallbackAPIVersion"):
                    self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
                else:
                    self.client = mqtt.Client(client_id=client_id)
                self.client.on_connect = self._on_connect
            except Exception:
                self.client = None
        else:
            self.client = None

    def _on_connect(self, client, userdata, flags, rc, *args):
        if rc == 0:
            self.connected = True

    def connect(self):
        if self.client:
            try:
                self.client.connect(self.broker_host, self.broker_port, keepalive=60)
                self.client.loop_start()
                self.connected = True
                print(f"MQTT Publicador conectado a {self.broker_host}:{self.broker_port}")
            except Exception as e:
                print(f"Aviso: No se pudo conectar al broker MQTT ({e}). Modo simulación local activo.")
                self.connected = False

    def publish_step(self, step_idx):
        poa, temp = self.data_loader.get_solar_at(step_idx)
        ws = self.data_loader.get_eolic_at(step_idx)
        vc = self.data_loader.get_hydro_at(step_idx)

        payloads = {
            "microgrid/meteorologia/solar": {"step": step_idx, "POA": poa, "T_amb": temp},
            "microgrid/meteorologia/eolica": {"step": step_idx, "Ws": ws},
            "microgrid/meteorologia/hidrica": {"step": step_idx, "Vc": vc}
        }

        if self.connected and self.client:
            for topic, data in payloads.items():
                self.client.publish(topic, json.dumps(data))

        return payloads

    def disconnect(self):
        if self.client and self.connected:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False

if __name__ == "__main__":
    pub = MQTTPublisher()
    pub.connect()
    p = pub.publish_step(10)
    print("Payloads MQTT paso 10:")
    print(json.dumps(p, indent=2))
    pub.disconnect()
