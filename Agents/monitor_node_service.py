import sys
import os
import time
import argparse
import csv
import json
import zmq

class MonitorNodeService:
    """
    Servicio del Nodo Monitor (alojado en RPi 5 - 10.0.0.155):
    - Oyente pasivo no invasivo (Subscriber).
    - Escucha el Reloj Maestro del PC Central (PUB 5556).
    - Escucha los canales de consenso P2P de los DERs (PUB 6001, 6002, 6003).
    - Registra la telemetria completa en CSV de alta resolucion para graficas de la tesis.
    - Soporte dinamico para redes de 6 u 8 nodos en Baja Tension (400 V).
    """
    def __init__(
        self,
        master_host: str = "10.0.0.156",
        port_pub: int = 5556,
        der_p2p_targets: list = None,
        output_csv: str = "output_data/telemetry_monitor.csv",
        num_nodes: int = 8,
        v_base: float = 400.0
    ):
        self.master_host = master_host
        self.port_pub = port_pub
        self.der_p2p_targets = der_p2p_targets or ["10.0.0.151:6001", "10.0.0.152:6002", "10.0.0.153:6003"]
        self.output_csv = output_csv
        self.num_nodes = int(num_nodes)
        self.v_base = float(v_base)
        self.csv_initialized = False
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

    def _init_csv(self, n_nodes=None):
        n_count = n_nodes or self.num_nodes
        headers = ["step", "time_sec", "f_sys_hz", "P_net_kW"]
        headers += [f"V{i}_pu" for i in range(1, n_count + 1)]
        headers += [f"V{i}_V" for i in range(1, n_count + 1)]
        headers += [
            "Q_ratio_1", "Q_ratio_2", "Q_ratio_3",
            "error_Q_12", "error_Q_23", "error_V_12", "error_V_23"
        ]
        with open(self.output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

    def run(self, max_steps=None):
        print("=" * 65)
        print(" SERVICIO DE TELEMETRIA Y OBSERVADOR DE RED (NODO MONITOR)")
        print(f" - Servidor Maestro:      tcp://{self.master_host}:{self.port_pub}")
        print(f" - Canales DERs P2P:      {self.der_p2p_targets}")
        print(f" - Nodos Monitoreados:    {self.num_nodes} (V_base = {self.v_base:.1f} V)")
        print(f" - Archivo de Salida CSV: {self.output_csv}")
        print("=" * 65)
        print("Iniciando captura pasiva de telemetria...\n")

        self.running = True
        step_count = 0
        der_states = {}

        try:
            while self.running:
                try:
                    clock_msg = self.sub_clock.recv_json()
                except zmq.Again:
                    print("[MONITOR] Esperando paquetes del PC Central...")
                    continue

                step_count += 1
                if max_steps and step_count > max_steps:
                    break

                step_idx = clock_msg.get("step", step_count)
                time_s = clock_msg.get("time_sec", step_idx * 0.5)
                f_sys = clock_msg.get("f_sys_hz", 60.0)
                p_net = clock_msg.get("P_net_w", 0.0) / 1000.0
                voltages = clock_msg.get("voltages", {})

                # Inicializar encabezado CSV dinámicamente según la cantidad de nodos recibida
                if not self.csv_initialized:
                    if voltages:
                        detected_max = max([int(k) for k in voltages.keys()])
                        actual_n = max(self.num_nodes, detected_max)
                    else:
                        actual_n = self.num_nodes
                    self.num_nodes = actual_n
                    self._init_csv(actual_n)
                    self.csv_initialized = True

                # Recoger ultimos paquetes de los DERs en la red
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

                # Extraer ratios de reactiva
                q1 = der_states.get(1, {}).get("Q_ratio", 0.0)
                q2 = der_states.get(2, {}).get("Q_ratio", 0.0)
                q3 = der_states.get(3, {}).get("Q_ratio", 0.0)

                err_q_12 = abs(q1 - q2)
                err_q_23 = abs(q2 - q3)

                v_pu = [voltages.get(str(i), {}).get("V_pu", 1.0) for i in range(1, self.num_nodes + 1)]
                v_volts = [voltages.get(str(i), {}).get("V_volts", self.v_base) for i in range(1, self.num_nodes + 1)]

                err_v_12 = abs(v_pu[0] - v_pu[1]) if len(v_pu) >= 2 else 0.0
                err_v_23 = abs(v_pu[1] - v_pu[2]) if len(v_pu) >= 3 else 0.0

                # Escribir fila en CSV
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

                if step_idx % 2 == 0:
                    v_min = min(v_pu) if v_pu else 1.0
                    v_max = max(v_pu) if v_pu else 1.0
                    print(f"[MONITOR] Paso {step_idx:04d} | f={f_sys:.3f}Hz | P_net={p_net:5.1f}kW | Err_Q(1-2)={err_q_12:.4f} | Err_Q(2-3)={err_q_23:.4f} | V_min={v_min:.4f}pu | V_max={v_max:.4f}pu")

        except KeyboardInterrupt:
            print("\nDeteniendo servicio monitor...")
        finally:
            self.sub_clock.close()
            self.sub_ders.close()
            self.context.term()
            print(f"Telemetria guardada en: {self.output_csv}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servicio del Nodo Monitor")
    parser.add_argument("--master-host", default="10.0.0.156", help="IP del PC Central")
    parser.add_argument("--port-pub", type=int, default=5556, help="Puerto PUB del reloj")
    parser.add_argument("--der-targets", nargs="*", default=["10.0.0.151:6001", "10.0.0.152:6002", "10.0.0.153:6003"], help="Canales P2P DERs")
    parser.add_argument("--output-csv", default="output_data/telemetry_monitor.csv", help="Ruta del archivo CSV")
    parser.add_argument("--num-nodes", type=int, default=8, help="Numero de nodos a monitorear (default: 8)")
    parser.add_argument("--v-base", type=float, default=400.0, help="Tension base en Voltios (default: 400.0 V)")
    parser.add_argument("--steps", type=int, default=None, help="Numero maximo de pasos")
    args = parser.parse_args()

    mon = MonitorNodeService(
        master_host=args.master_host,
        port_pub=args.port_pub,
        der_p2p_targets=args.der_targets,
        output_csv=args.output_csv,
        num_nodes=args.num_nodes,
        v_base=args.v_base
    )
    mon.run(max_steps=args.steps)
