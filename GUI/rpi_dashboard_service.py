import sys
import os
import time
import argparse
import csv
import json
import threading
import http.server
import socketserver
from urllib.parse import urlparse
import zmq

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

GUI_DIR = os.path.dirname(os.path.abspath(__file__))

# Estado global compartido en memoria para la API REST del Dashboard
latest_telemetry_state = {
    "current_step": 0,
    "time_sec": 0.0,
    "f_sys_hz": 60.0,
    "P_net_kW": 0.0,
    "hold_mode": "ZFOH",
    "zfoh_lambda": 0.70,
    "network_profile": "LAN_ETHERNET",
    "latest_result": {
        "step": 0,
        "voltages": {
            "1": {"V_volts": 13800.0, "V_pu": 1.0000, "P": 0.0, "Q": 0.0},
            "2": {"V_volts": 13757.0, "V_pu": 0.9969, "P": 1748.0, "Q": 0.0},
            "3": {"V_volts": 13761.0, "V_pu": 0.9972, "P": 0.0, "Q": 0.0},
            "4": {"V_volts": 13758.0, "V_pu": 0.9970, "P": -2.85, "Q": -0.94},
            "5": {"V_volts": 13761.0, "V_pu": 0.9972, "P": -1.96, "Q": -0.40},
            "6": {"V_volts": 13763.0, "V_pu": 0.9974, "P": -1.47, "Q": -0.30}
        },
        "network_stats": {
            "profile": "LAN_ETHERNET",
            "avg_delay_ms": 1.2,
            "packet_loss_ratio": 0.0
        }
    },
    "q_ratios": {"1": 0.0, "2": 0.0, "3": 0.0},
    "errors": {"err_q_12": 0.0, "err_q_23": 0.0, "err_v_12": 0.0, "err_v_23": 0.0},
    "logs": [
        {"timestamp": time.strftime("%H:%M:%S"), "message": "Servicio de Dashboard & Storage RPi DATA inicializado.", "level": "info"}
    ]
}

state_lock = threading.Lock()


class DashboardHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=GUI_DIR, **kwargs)

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path in ["/api/telemetry/live", "/api/state"]:
            with state_lock:
                copy_state = dict(latest_telemetry_state)
            self._send_json(copy_state)
            return

        elif parsed.path == "/api/status":
            self._send_json({
                "status": "ONLINE",
                "node": "DATA (10.0.0.160)",
                "role": "Almacenamiento y Dashboard Web",
                "uptime_s": time.time()
            })
            return

        elif parsed.path == "/api/export":
            export_path = os.path.abspath(os.path.join(GUI_DIR, "..", "output_data", "telemetry_monitor.csv"))
            if os.path.exists(export_path):
                with open(export_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="telemetry_monitor.csv"')
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
                return
            else:
                self._send_json({"error": "No telemetry file yet"}, 404)
                return

        # Redirigir raiz a web_dashboard.html
        if parsed.path in ["", "/"]:
            self.send_response(302)
            self.send_header("Location", "/web_dashboard.html")
            self.end_headers()
            return

        super().do_GET()


class ReusableThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_web_server(host="0.0.0.0", port=8000):
    try:
        httpd = ReusableThreadingServer((host, port), DashboardHTTPHandler)
        print(f" [WEB] Servidor Dashboard HTTP escuchando en http://{host}:{port}/web_dashboard.html")
        httpd.serve_forever()
    except Exception as e:
        print(f" [WEB ERROR] No se pudo iniciar servidor web en puerto {port}: {e}")


class RPiDataService:
    """
    Servicio Integrado para la Raspberry Pi DATA (10.0.0.160):
      1. Servidor Web Dashboard (HTTP en puerto 8000 para acceso desde cualquier navegador).
      2. Suscriptor ZeroMQ del Reloj Maestro (PC Central) y canales DERs P2P.
      3. Registro en tiempo real de telemetría a disco (CSV).
    """
    def __init__(
        self,
        master_host: str = "10.0.0.156",
        port_pub: int = 5556,
        web_port: int = 8000,
        der_p2p_targets: list = None,
        output_csv: str = "output_data/telemetry_monitor.csv"
    ):
        self.master_host = master_host
        self.port_pub = port_pub
        self.web_port = int(web_port)
        self.der_p2p_targets = der_p2p_targets or ["10.0.0.151:6001", "10.0.0.152:6002", "10.0.0.153:6003"]
        self.output_csv = os.path.abspath(output_csv)
        os.makedirs(os.path.dirname(self.output_csv) or ".", exist_ok=True)

        self.context = zmq.Context()

        # Socket SUB al PC Central
        self.sub_clock = self.context.socket(zmq.SUB)
        self.sub_clock.setsockopt(zmq.SUBSCRIBE, b"")
        self.sub_clock.setsockopt(zmq.RCVTIMEO, 3000)
        self.sub_clock.connect(f"tcp://{self.master_host}:{self.port_pub}")

        # Socket SUB a los DERs P2P
        self.sub_ders = self.context.socket(zmq.SUB)
        self.sub_ders.setsockopt(zmq.SUBSCRIBE, b"")
        self.sub_ders.setsockopt(zmq.RCVTIMEO, 50)
        for target in self.der_p2p_targets:
            self.sub_ders.connect(f"tcp://{target}")

        self.poller = zmq.Poller()
        self.poller.register(self.sub_ders, zmq.POLLIN)

        self.running = False
        self._init_csv()

    def _init_csv(self):
        headers = [
            "step", "time_sec", "f_sys_hz", "P_net_kW",
            "V1_pu", "V2_pu", "V3_pu", "V4_pu", "V5_pu", "V6_pu",
            "V1_V", "V2_V", "V3_V", "V4_V", "V5_V", "V6_V",
            "Q_ratio_1", "Q_ratio_2", "Q_ratio_3",
            "error_Q_12", "error_Q_23", "error_V_12", "error_V_23"
        ]
        with open(self.output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

    def run(self, max_steps=None):
        print("=" * 65)
        print(" RASPBERRY PI DATA: DASHBOARD WEB + STORAGE TELEMETRIA")
        print(f" - Servidor Maestro:      tcp://{self.master_host}:{self.port_pub}")
        print(f" - Canales DERs P2P:      {self.der_p2p_targets}")
        print(f" - Dashboard Web:         http://0.0.0.0:{self.web_port}/web_dashboard.html")
        print(f" - Archivo Telemetria:    {self.output_csv}")
        print("=" * 65)

        # Iniciar servidor web HTTP en segundo plano
        web_thread = threading.Thread(target=start_web_server, kwargs={"host": "0.0.0.0", "port": self.web_port}, daemon=True)
        web_thread.start()

        self.running = True
        step_count = 0
        der_states = {}

        try:
            while self.running:
                step_count += 1
                if max_steps and step_count > max_steps:
                    print(f"\n[DATA DASHBOARD] Simulacion de {max_steps} pasos finalizada exitosamente.")
                    print(f" [WEB] El Dashboard permanece 100% activo en http://0.0.0.0:{self.web_port}/web_dashboard.html")
                    print(" Esperando nueva sesion de simulacion...\n")
                    # Mantener el Dashboard HTTP activo indefinidamente hasta nueva simulacion
                    while self.running:
                        try:
                            clock_msg = self.sub_clock.recv_json()
                            if clock_msg and clock_msg.get("step", 999) <= 2:
                                print("\n[DATA DASHBOARD] Nueva sesion de simulacion detectada. Reiniciando contador...")
                                step_count = 1
                                break
                        except zmq.Again:
                            time.sleep(0.5)
                            continue

                try:
                    clock_msg = self.sub_clock.recv_json()
                except zmq.Again:
                    continue

                step_idx = clock_msg.get("step", step_count)
                time_s = clock_msg.get("time_sec", step_idx * 0.5)
                f_sys = clock_msg.get("f_sys_hz", 60.0)
                p_net = clock_msg.get("P_net_w", 0.0) / 1000.0
                voltages = clock_msg.get("voltages", {})

                # Recoger ultimos paquetes de los DERs en la red P2P
                time.sleep(0.015)
                while True:
                    socks = dict(self.poller.poll(timeout=10))
                    if self.sub_ders in socks and socks[self.sub_ders] == zmq.POLLIN:
                        try:
                            der_msg = self.sub_ders.recv_json()
                            s_id = der_msg.get("sender_id")
                            if s_id:
                                der_states[s_id] = der_msg
                        except Exception:
                            break
                    else:
                        break

                q1 = der_states.get(1, {}).get("Q_ratio", 0.0)
                q2 = der_states.get(2, {}).get("Q_ratio", 0.0)
                q3 = der_states.get(3, {}).get("Q_ratio", 0.0)

                err_q_12 = abs(q1 - q2)
                err_q_23 = abs(q2 - q3)

                v_pu = [voltages.get(str(i), {}).get("V_pu", 1.0) for i in range(1, 7)]
                v_volts = [voltages.get(str(i), {}).get("V_volts", 13800.0) for i in range(1, 7)]

                err_v_12 = abs(v_pu[0] - v_pu[1])
                err_v_23 = abs(v_pu[1] - v_pu[2])

                # 1. Escribir fila en CSV
                row = [
                    step_idx, round(time_s, 2), round(f_sys, 4), round(p_net, 2),
                    *[round(x, 5) for x in v_pu],
                    *[round(x, 2) for x in v_volts],
                    round(q1, 4), round(q2, 4), round(q3, 4),
                    round(err_q_12, 4), round(err_q_23, 4),
                    round(err_v_12, 5), round(err_v_23, 5)
                ]
                with open(self.output_csv, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(row)

                # 2. Actualizar estado en memoria para la API del Dashboard en vivo
                with state_lock:
                    latest_telemetry_state["current_step"] = step_idx
                    latest_telemetry_state["time_sec"] = round(time_s, 2)
                    latest_telemetry_state["f_sys_hz"] = round(f_sys, 3)
                    latest_telemetry_state["P_net_kW"] = round(p_net, 2)
                    latest_telemetry_state["latest_result"] = {
                        "step": step_idx,
                        "voltages": {
                            str(i): {
                                "V_pu": round(v_pu[i-1], 5),
                                "V_volts": round(v_volts[i-1], 2)
                            } for i in range(1, 7)
                        },
                        "network_stats": {
                            "profile": "LAN_ETHERNET",
                            "avg_delay_ms": 1.2,
                            "packet_loss_ratio": 0.0
                        }
                    }
                    latest_telemetry_state["q_ratios"] = {"1": round(q1, 4), "2": round(q2, 4), "3": round(q3, 4)}
                    latest_telemetry_state["errors"] = {
                        "err_q_12": round(err_q_12, 4),
                        "err_q_23": round(err_q_23, 4),
                        "err_v_12": round(err_v_12, 5),
                        "err_v_23": round(err_v_23, 5)
                    }
                    if step_idx % 4 == 0:
                        log_msg = f"Paso {step_idx:04d} | f={f_sys:.2f}Hz | P_net={p_net:5.1f}kW | V_min={min(v_pu):.4f}pu"
                        latest_telemetry_state["logs"].append({
                            "timestamp": time.strftime("%H:%M:%S"),
                            "message": log_msg,
                            "level": "info"
                        })
                        if len(latest_telemetry_state["logs"]) > 50:
                            latest_telemetry_state["logs"].pop(0)

                if step_idx % 2 == 0:
                    print(f"[DATA DASHBOARD] Paso {step_idx:04d} | f={f_sys:.3f}Hz | P_net={p_net:5.1f}kW | V_min={min(v_pu):.4f}pu | Web: OK")

        except KeyboardInterrupt:
            print("\nDeteniendo servicio de Dashboard y Storage...")
        finally:
            self.sub_clock.close()
            self.sub_ders.close()
            self.context.term()
            print(f"Servicio finalizado. Telemetria guardada en: {self.output_csv}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servicio Integrado RPi DATA: Dashboard + Storage")
    parser.add_argument("--master-host", default="10.0.0.156", help="IP del PC Central")
    parser.add_argument("--port-pub", type=int, default=5556, help="Puerto PUB del reloj ZMQ")
    parser.add_argument("--web-port", type=int, default=8000, help="Puerto HTTP del Dashboard Web")
    parser.add_argument("--der-targets", nargs="*", default=["10.0.0.151:6001", "10.0.0.152:6002", "10.0.0.153:6003"], help="Canales P2P DERs")
    parser.add_argument("--output-csv", default="output_data/telemetry_monitor.csv", help="Ruta archivo CSV")
    parser.add_argument("--steps", type=int, default=None, help="Numero maximo de pasos")
    args = parser.parse_args()

    service = RPiDataService(
        master_host=args.master_host,
        port_pub=args.port_pub,
        web_port=args.web_port,
        der_p2p_targets=args.der_targets,
        output_csv=args.output_csv
    )
    service.run(max_steps=args.steps)
