import sys
import os
import json
import time
from typing import Optional, Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from GUI.mqtt_publisher import MQTTPublisher
from GUI.influx_telemetry import InfluxTelemetryLogger
from Central_PC.master_clock_zmq import MasterClockZMQ
from Docker.docker_compose_generator import DockerComposeGenerator
from Agents.network_impairment_proxy import NetworkImpairmentProxy

class GUICommandCenter:
    """
    Centro de Mando del Sistema Multi-Agente (MAS) de la Microrred Distribuida.
    Permite:
      - Cargar perfiles de demanda y series temporales meteorológicas (.csv/.xlsx).
      - Seleccionar topología de red (Red BT 400V, Red MT 20kV o Red BT Mallada).
      - Conmutar modo de operación (ONLINE Conectado a Red vs OFFLINE Isla).
      - Seleccionar solucionador del PC Central (Modo A FBS vs Modo B Sensibilidad).
      - Seleccionar la configuración de Malla para el Modo B (RADIAL, RING_ZBUS, FULL_JACOBIAN).
      - Seleccionar el Perfil de Canal de Comunicación (IDEAL, LAN_ETHERNET, INDUSTRIAL_WIFI, SEVERE_STRESS, CRITICAL_PARTITION).
      - Orquestación y despliegue automático de contenedores Docker con 1 clic.
    """
    def __init__(
        self,
        topology_csv: Optional[str] = None,
        mode: str = "ONLINE",
        solver_mode: str = "FBS",
        mesh_type: str = "RADIAL",
        network_profile: str = "IDEAL"
    ):
        if topology_csv is None:
            topology_csv = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "topologia_BT_4nodos.csv"))
        
        self.topology_csv = topology_csv
        self.mode = mode.upper()
        self.solver_mode = solver_mode.upper()
        self.mesh_type = mesh_type.upper()
        self.network_profile = network_profile.upper()
        
        self.mqtt_pub = MQTTPublisher()
        self.telemetry = InfluxTelemetryLogger()
        self.master_clock = None
        self.compose_generator = DockerComposeGenerator(self.topology_csv)
        self.network_proxy = NetworkImpairmentProxy(profile=self.network_profile)

    def set_topology(self, csv_path: str) -> bool:
        """Asigna un nuevo archivo de topología."""
        if os.path.exists(csv_path):
            self.topology_csv = csv_path
            self.compose_generator = DockerComposeGenerator(csv_path)
            return True
        return False

    def set_network_profile(self, profile: str):
        """Actualiza el perfil de canal de comunicación."""
        self.network_profile = profile.upper()
        self.network_proxy.set_profile(self.network_profile)

    def deploy_containers(self, output_compose: str = "docker-compose.yml") -> str:
        """Orquesta y genera el manifiesto de contenedores desacoplados en 1 clic con emulación de red."""
        profile_params = self.network_proxy.PROFILES.get(self.network_profile, {})
        out_file = self.compose_generator.generate_yaml(
            output_compose,
            mode=self.mode,
            network_profile=self.network_profile,
            network_delay_ms=profile_params.get("base_latency_ms", 0.0),
            packet_loss_rate=profile_params.get("loss_rate", 0.0)
        )
        print(f"[CENTRO DE MANDO] Despliegue de 1-Clic: Manifiesto {out_file} generado exitosamente (Perfil Red: {self.network_profile}).")
        return out_file

    def run_simulation(self, max_steps: int = 5, port_rep: int = 5555, port_pub: int = 5556):
        """Ejecuta una ronda de co-simulación coordinada con telemetría MQTT, emulación de canal e InfluxDB."""
        print(f"\n=======================================================")
        print(f"  CENTRO DE MANDO: Iniciando Simulación")
        print(f"  Modo: {self.mode} | Solver: {self.solver_mode} [Malla={self.mesh_type}]")
        print(f"  Canal de Comunicación: {self.network_profile}")
        print(f"=======================================================")

        self.mqtt_pub.connect()
        self.master_clock = MasterClockZMQ(
            self.topology_csv,
            mode=self.solver_mode,
            mesh_type=self.mesh_type,
            port_rep=port_rep,
            port_pub=port_pub
        )

        injections = {
            "2": {"P": 10000.0, "Q": 2000.0},
            "3": {"P": 5000.0, "Q": 1000.0},
            "4": {"P": -15000.0, "Q": -3000.0}
        }

        history = []

        for step in range(1, max_steps + 1):
            mqtt_payloads = self.mqtt_pub.publish_step(step)
            master_res = self.master_clock.run_step(injections)

            # Extraer métricas de salud del canal de comunicación
            net_stats = self.network_proxy.get_network_health()

            telemetry_rec = self.telemetry.log_step(
                step_idx=step,
                mode=self.mode,
                voltages=master_res["voltages"],
                power_injections=injections
            )

            history.append({
                "step": step,
                "voltages": master_res["voltages"],
                "mqtt": mqtt_payloads,
                "network_stats": net_stats
            })

            print(f"[PASO {step}] Tensiones: Nodo 1: {master_res['voltages'].get(1, {}).get('V_volts')} V, "
                  f"Nodo 2: {master_res['voltages'].get(2, {}).get('V_volts')} V, "
                  f"Nodo 4: {master_res['voltages'].get(4, {}).get('V_volts')} V | "
                  f"Loss: {net_stats['packet_loss_ratio']*100:.1f}%")

        self.master_clock.close()
        self.mqtt_pub.disconnect()
        self.telemetry.close()

        print(f"Simulación de {max_steps} pasos completada exitosamente.\n")
        return history

if __name__ == "__main__":
    center = GUICommandCenter(
        mode="ONLINE",
        solver_mode="SENSITIVITY",
        mesh_type="RING_ZBUS",
        network_profile="INDUSTRIAL_WIFI"
    )
    center.deploy_containers("docker-compose.gui_test.yml")
    center.run_simulation(max_steps=3)
