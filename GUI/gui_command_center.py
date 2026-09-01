import sys
import os
import json
import time
import threading
from typing import Optional, Dict, Any, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from GUI.mqtt_publisher import MQTTPublisher
from GUI.influx_telemetry import InfluxTelemetryLogger
from Central_PC.master_clock_zmq import MasterClockZMQ
from Docker.docker_compose_generator import DockerComposeGenerator
from Agents.network_impairment_proxy import NetworkImpairmentProxy
from Scripts.deploy_raspberry import RaspberryDeployer

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
      - Seleccionar Esquemas de Reconstrucción Multitasa: ZOH, FOH, ZFOH (con parámetro lambda).
      - Orquestación y despliegue automático de contenedores Docker locales y en clúster Raspberry Pi 5 con 1 clic.
      - Ejecución continua asíncrona (background thread) para integración fluida con API Web / Tkinter.
      - Exportación de telemetría a formatos CSV y JSON.
    """
    def __init__(
        self,
        topology_csv: Optional[str] = None,
        mode: str = "ONLINE",
        solver_mode: str = "FBS",
        mesh_type: str = "RADIAL",
        network_profile: str = "IDEAL",
        hold_mode: str = "ZOH",
        zfoh_lambda: float = 0.7,
        rpi_host: str = "192.168.1.10",
        rpi_user: str = "jhonclavijotro",
        rpi_port: int = 22,
        master_clock_host: str = "192.168.1.100"
    ):
        if topology_csv is None:
            topology_csv = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "topologia_BT_4nodos.csv"))
        
        self.topology_csv = topology_csv
        self.mode = mode.upper()
        self.solver_mode = solver_mode.upper()
        self.mesh_type = mesh_type.upper()
        self.network_profile = network_profile.upper()
        self.hold_mode = hold_mode.upper()
        self.zfoh_lambda = float(zfoh_lambda)
        
        # Parámetros Raspberry Pi
        self.rpi_host = rpi_host
        self.rpi_user = rpi_user
        self.rpi_port = rpi_port
        self.master_clock_host = master_clock_host
        
        self.mqtt_pub = MQTTPublisher()
        self.telemetry = InfluxTelemetryLogger()
        self.master_clock = None
        self.compose_generator = DockerComposeGenerator(self.topology_csv)
        self.network_proxy = NetworkImpairmentProxy(profile=self.network_profile)

        # Control de simulación en segundo plano
        self._sim_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_running = False
        self.current_step = 0
        self.logs_buffer: List[Dict[str, Any]] = []
        self.latest_result: Dict[str, Any] = {
            "voltages": {
                "1": {"V_volts": 400.0, "V_pu": 1.0},
                "2": {"V_volts": 399.98, "V_pu": 0.9999},
                "3": {"V_volts": 401.89, "V_pu": 1.0047},
                "4": {"V_volts": 405.73, "V_pu": 1.0143}
            },
            "power": {
                "1": {"P": 25000.0, "Q": 5000.0},
                "2": {"P": 10000.0, "Q": 2000.0},
                "3": {"P": 5000.0, "Q": 1000.0},
                "4": {"P": -15000.0, "Q": -3000.0}
            },
            "network_stats": {
                "profile": self.network_profile,
                "avg_delay_ms": 0.0,
                "packet_loss_ratio": 0.0
            }
        }

    def set_topology(self, csv_path: str) -> bool:
        """Asigna un nuevo archivo de topología."""
        if os.path.exists(csv_path):
            self.topology_csv = csv_path
            self.compose_generator = DockerComposeGenerator(csv_path)
            self._log_event(f"Topología actualizada: {os.path.basename(csv_path)}")
            return True
        return False

    def set_mode(self, mode: str):
        self.mode = mode.upper()
        self._log_event(f"Modo de operación cambiado a: {self.mode}")

    def set_solver_mode(self, solver_mode: str):
        self.solver_mode = solver_mode.upper()
        self._log_event(f"Solucionador cambiado a: {self.solver_mode}")

    def set_mesh_type(self, mesh_type: str):
        self.mesh_type = mesh_type.upper()
        self._log_event(f"Configuración de Malla cambiada a: {self.mesh_type}")

    def set_network_profile(self, profile: str):
        """Actualiza el perfil de canal de comunicación."""
        self.network_profile = profile.upper()
        self.network_proxy.set_profile(self.network_profile)
        self._log_event(f"Perfil de canal ciberfísico establecido en: {self.network_profile}")

    def set_hold_mode(self, hold_mode: str, zfoh_lambda: Optional[float] = None):
        """Actualiza el esquema de reconstrucción/extrapolación (ZOH, FOH, ZFOH)."""
        self.hold_mode = hold_mode.upper()
        if zfoh_lambda is not None:
            self.zfoh_lambda = max(0.0, min(1.0, float(zfoh_lambda)))
        self._log_event(f"Esquema Hold establecido en: {self.hold_mode} (Lambda = {self.zfoh_lambda:.2f})")

    def set_rpi_config(self, host: str, user: str, port: int = 22, master_clock_host: str = "192.168.1.100"):
        """Actualiza las credenciales y dirección de la Raspberry Pi 5."""
        self.rpi_host = host
        self.rpi_user = user
        self.rpi_port = int(port)
        self.master_clock_host = master_clock_host
        self._log_event(f"Configuración RPi 5 actualizada: {self.rpi_user}@{self.rpi_host}:{self.rpi_port}")

    def test_rpi_connection(self) -> Dict[str, Any]:
        """Prueba de diagnóstico de conexión SSH con la Raspberry Pi 5."""
        deployer = RaspberryDeployer(
            host=self.rpi_host,
            user=self.rpi_user,
            port=self.rpi_port,
            master_clock_host=self.master_clock_host,
            hold_mode=self.hold_mode,
            zfoh_lambda=self.zfoh_lambda
        )
        res = deployer.test_connection()
        self._log_event(res["message"], "INFO" if res["connected"] else "WARN")
        return res

    def deploy_to_raspberry(
        self,
        host: Optional[str] = None,
        user: Optional[str] = None,
        port: Optional[int] = None,
        master_clock_host: Optional[str] = None
    ) -> Dict[str, Any]:
        """Orquesta el despliegue automático hacia la Raspberry Pi 5 con 1 clic."""
        h = host or self.rpi_host
        u = user or self.rpi_user
        p = port or self.rpi_port
        m = master_clock_host or self.master_clock_host

        self._log_event(f"Iniciando despliegue hacia Raspberry Pi ({u}@{h})...")
        deployer = RaspberryDeployer(
            host=h,
            user=u,
            port=p,
            master_clock_host=m,
            hold_mode=self.hold_mode,
            zfoh_lambda=self.zfoh_lambda
        )
        
        diag = deployer.test_connection()
        if not diag["connected"]:
            return {
                "success": False,
                "message": f"Conexión fallida con {u}@{h}. Verifique red y credenciales SSH.",
                "details": diag
            }

        sync_res = deployer.sync_code()
        if not sync_res["success"]:
            return {
                "success": False,
                "message": f"Fallo al sincronizar archivos a la RPi: {sync_res.get('message')}",
                "details": sync_res
            }

        deploy_res = deployer.deploy_docker()
        msg = f"Despliegue RPi completado: {deploy_res.get('message')}"
        self._log_event(msg, "INFO" if deploy_res["success"] else "ERROR")
        return {
            "success": deploy_res["success"],
            "message": msg,
            "details": deploy_res
        }

    def deploy_containers(self, output_compose: str = "docker-compose.yml") -> str:
        """Orquesta y genera el manifiesto de contenedores desacoplados en 1 clic con emulación de red y Hold."""
        profile_params = self.network_proxy.PROFILES.get(self.network_profile, {})
        out_file = self.compose_generator.generate_yaml(
            output_compose,
            mode=self.mode,
            network_profile=self.network_profile,
            network_delay_ms=profile_params.get("base_latency_ms", 0.0),
            packet_loss_rate=profile_params.get("loss_rate", 0.0),
            hold_mode=self.hold_mode,
            zfoh_lambda=self.zfoh_lambda,
            master_clock_host=self.master_clock_host
        )
        msg = f"Despliegue 1-Clic: Manifiesto {out_file} generado (Hold: {self.hold_mode}, Lambda: {self.zfoh_lambda:.2f}, Perfil: {self.network_profile})."
        self._log_event(msg)
        print(f"[CENTRO DE MANDO] {msg}")
        return out_file

    def _log_event(self, msg: str, level: str = "INFO"):
        entry = {
            "timestamp": time.strftime("%H:%M:%S"),
            "level": level,
            "message": msg
        }
        self.logs_buffer.append(entry)
        if len(self.logs_buffer) > 100:
            self.logs_buffer.pop(0)

    def start_simulation_thread(self, max_steps: Optional[int] = None, step_delay: float = 0.5):
        """Inicia la co-simulación en un hilo de fondo no bloqueante."""
        if self._is_running:
            return False

        self._stop_event.clear()
        self._is_running = True
        self._sim_thread = threading.Thread(
            target=self._run_simulation_worker,
            args=(max_steps, step_delay),
            daemon=True
        )
        self._sim_thread.start()
        self._log_event("Co-simulación asíncrona iniciada a 500 ms.")
        return True

    def stop_simulation(self):
        """Solicita la detención de la simulación activa."""
        if self._is_running:
            self._stop_event.set()
            self._is_running = False
            self._log_event("Solicitud de detención de co-simulación enviada.")

    def is_simulation_active(self) -> bool:
        return self._is_running

    def _run_simulation_worker(self, max_steps: Optional[int], step_delay: float):
        """Bucle de ejecución interno para el hilo de fondo."""
        try:
            self.mqtt_pub.connect()
        except Exception as e:
            self._log_event(f"Aviso MQTT: {e}", "WARN")

        try:
            self.master_clock = MasterClockZMQ(
                self.topology_csv,
                mode=self.solver_mode,
                mesh_type=self.mesh_type,
                port_rep=5555,
                port_pub=5556
            )
        except Exception as e:
            self._log_event(f"Aviso ZMQ: {e}", "WARN")

        injections = {
            "2": {"P": 10000.0, "Q": 2000.0},
            "3": {"P": 5000.0, "Q": 1000.0},
            "4": {"P": -15000.0, "Q": -3000.0}
        }

        step = 0
        while not self._stop_event.is_set():
            step += 1
            self.current_step = step
            if max_steps and step > max_steps:
                break

            try:
                mqtt_payloads = self.mqtt_pub.publish_step(step)
            except Exception:
                mqtt_payloads = {}

            if self.master_clock:
                try:
                    master_res = self.master_clock.run_step(injections)
                    voltages = master_res.get("voltages", self.latest_result["voltages"])
                except Exception:
                    voltages = self.latest_result["voltages"]
            else:
                voltages = self.latest_result["voltages"]

            # Emular perturbación de red en el proxy y capturar telemetría ciberfísica
            net_stats = self.network_proxy.get_network_health()

            telemetry_rec = self.telemetry.log_step(
                step_idx=step,
                mode=self.mode,
                voltages=voltages,
                power_injections=injections,
                network_stats=net_stats
            )

            self.latest_result = {
                "step": step,
                "voltages": voltages,
                "power": injections,
                "network_stats": net_stats,
                "mqtt": mqtt_payloads
            }

            v_summary = ", ".join([f"N{k}={v.get('V_volts', 400.0):.2f}V" for k, v in voltages.items() if isinstance(v, dict)])
            self._log_event(f"Paso {step}: {v_summary} | Pérdida: {net_stats.get('packet_loss_ratio', 0.0)*100:.1f}%")

            time.sleep(step_delay)

        self._is_running = False
        if self.master_clock:
            try:
                self.master_clock.close()
            except Exception:
                pass
        try:
            self.mqtt_pub.disconnect()
        except Exception:
            pass

        self._log_event(f"Co-simulación finalizada tras {step} pasos.")

    def run_simulation(self, max_steps: int = 5, port_rep: int = 5555, port_pub: int = 5556):
        """Ejecuta una ronda síncrona de co-simulación (útil para scripts de consola o tests)."""
        print(f"\n=======================================================")
        print(f"  CENTRO DE MANDO: Iniciando Simulación Síncrona")
        print(f"  Modo: {self.mode} | Solver: {self.solver_mode} [Malla={self.mesh_type}]")
        print(f"  Canal de Comunicación: {self.network_profile}")
        print(f"=======================================================")

        try:
            self.mqtt_pub.connect()
        except Exception:
            pass

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
            self.current_step = step
            try:
                mqtt_payloads = self.mqtt_pub.publish_step(step)
            except Exception:
                mqtt_payloads = {}

            master_res = self.master_clock.run_step(injections)
            net_stats = self.network_proxy.get_network_health()

            telemetry_rec = self.telemetry.log_step(
                step_idx=step,
                mode=self.mode,
                voltages=master_res["voltages"],
                power_injections=injections,
                network_stats=net_stats
            )

            step_data = {
                "step": step,
                "voltages": master_res["voltages"],
                "power": injections,
                "mqtt": mqtt_payloads,
                "network_stats": net_stats
            }
            self.latest_result = step_data
            history.append(step_data)

            self._log_event(f"Paso Síncrono {step}: V1={master_res['voltages'].get(1, {}).get('V_volts')} V, Loss={net_stats['packet_loss_ratio']*100:.1f}%")

        self.master_clock.close()
        try:
            self.mqtt_pub.disconnect()
        except Exception:
            pass

        return history

    def get_current_state(self) -> Dict[str, Any]:
        """Obtiene una captura instantánea del estado para la API REST o interfaz."""
        return {
            "is_running": self._is_running,
            "current_step": self.current_step,
            "mode": self.mode,
            "solver_mode": self.solver_mode,
            "mesh_type": self.mesh_type,
            "network_profile": self.network_profile,
            "hold_mode": self.hold_mode,
            "zfoh_lambda": self.zfoh_lambda,
            "rpi_host": self.rpi_host,
            "rpi_user": self.rpi_user,
            "rpi_port": self.rpi_port,
            "master_clock_host": self.master_clock_host,
            "topology_file": os.path.basename(self.topology_csv),
            "latest_result": self.latest_result,
            "logs": self.logs_buffer[-25:]  # Últimos 25 logs
        }

    def export_session_data(self, filepath: str, fmt: str = "csv") -> str:
        """Exporta el historial de simulación."""
        if fmt.lower() == "json":
            return self.telemetry.export_to_json(filepath)
        return self.telemetry.export_to_csv(filepath)

if __name__ == "__main__":
    center = GUICommandCenter(
        mode="ONLINE",
        solver_mode="SENSITIVITY",
        mesh_type="RING_ZBUS",
        network_profile="INDUSTRIAL_WIFI"
    )
    center.deploy_containers("docker-compose.gui_test.yml")
    center.run_simulation(max_steps=3)
    out_file = center.export_session_data("output_data/gui_session_test.csv")
    print(f"Sesión exportada a: {out_file}")

