import sys
import os
import csv
import time
import socket
import json
import argparse
import signal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Central_PC.master_clock_zmq import MasterClockZMQ
from Agents.monitor_node_service import build_s40_headers, build_s40_row

def get_local_ip(target_subnet="10.0.0."):
    """Detecta automáticamente la IP local dentro de la subred especificada."""
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if ip.startswith(target_subnet):
                return ip
    except Exception:
        pass
    # Fallback probando conexión de socket saliente
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.0.0.151", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "10.0.0.156"


class PowerFlowClockServer:
    """
    Servidor Autónomo para el PC Central:
    - Ejecuta el Flujo de Potencia Radial BT (FBS) a 400 V.
    - Sincroniza el Reloj Maestro ZeroMQ a 500 ms (2 Hz).
    - Opera en Modo Isla (OFFLINE) con Nodo 1 (Diésel) como barra Slack.
    """
    def __init__(
        self,
        topology_path: str,
        v_base: float = 400.0,
        s_base: float = 10000.0,
        port_rep: int = 5555,
        port_pub: int = 5556,
        step_dt: float = 0.5,
        operating_mode: str = "OFFLINE",
        backup_csv: str = "output_data/telemetry_central_backup.csv",
        fast_mode: bool = False
    ):
        self.topology_path = topology_path
        self.v_base = float(v_base)
        self.s_base = float(s_base)
        self.port_rep = port_rep
        self.port_pub = port_pub
        self.step_dt = float(step_dt)
        self.operating_mode = operating_mode.upper()
        self.backup_csv = backup_csv
        self.fast_mode = fast_mode
        self.local_ip = get_local_ip()

        self.master = MasterClockZMQ(
            topology_csv=self.topology_path,
            mode="FBS",
            mesh_type="RADIAL",
            V_base=self.v_base,
            S_base=self.s_base,
            port_rep=self.port_rep,
            port_pub=self.port_pub,
            comm_scenario="IDEAL"
        )
        self.master.dt = self.step_dt
        self.master.H_sys = 6.0
        self.master.D_sys = 12.0
        self.master.set_operating_mode(self.operating_mode, slack_node=1, V_slack=1.0)
        self.running = False

    def run(self, max_steps: int = None):
        print("=" * 65)
        print(" SERVIDOR CENTRAL PC: SOLVER BT (400 V) & RELOJ MAESTRO ZMQ")
        print("=" * 65)
        print(f" - IP PC Central:        {self.local_ip}")
        print(f" - Topologia:            {os.path.basename(self.topology_path)}")
        print(f" - Nivel de Tension:     {self.v_base / 1000.0:.1f} kV ({self.v_base} V)")
        print(f" - Potencia Base:        {self.s_base / 1000.0:.0f} kVA")
        print(f" - Modo de Operacion:    {self.operating_mode} (Barra Slack: Nodo 1 Diesel)")
        print(f" - Sockets ZMQ:          REP :{self.port_rep} (Inyecciones), PUB :{self.port_pub} (Reloj/V_pcc)")
        print(f" - Periodo Maestro (H):  {self.step_dt * 1000.0:.0f} ms ({1.0 / self.step_dt:.1f} Hz)")
        print("=" * 65)
        print("Servidor iniciado. Esperando sincronizacion de Raspberry Pis...\n")

        self.running = True
        step = 0
        last_injections = {}
        der_meta = {}
        load_totals = {"P_load_total_w": 0.0, "Q_load_total_var": 0.0}
        seen_senders = set()
        csv_initialized = False
        if self.backup_csv:
            os.makedirs(os.path.dirname(self.backup_csv) or ".", exist_ok=True)

        # Breve margen inicial para completar suscripción ZMQ PUB/SUB (slow-joiner) antes del paso 1
        time.sleep(1.0)
        t_next = time.perf_counter()

        import zmq
        poller = zmq.Poller()
        poller.register(self.master.rep_socket, zmq.POLLIN)

        try:
            while self.running:
                step += 1
                if max_steps and step > max_steps:
                    break

                step_wall_start = time.perf_counter()
                t_next += self.step_dt

                injections = dict(last_injections)
                sample_idx = step - 1
                time_s = round(sample_idx * self.step_dt, 2)
                extra_payload = {
                    "sample_idx": sample_idx,
                    "time_s": time_s,
                    "der_meta": {str(k): v for k, v in der_meta.items()},
                    "P_load_total_w": round(load_totals["P_load_total_w"], 2),
                    "Q_load_total_var": round(load_totals["Q_load_total_var"], 2),
                }

                # 1. Resolver flujo de potencia FBS y emitir tick de reloj del paso actual
                result = self.master.run_step(injections, extra_payload=extra_payload)

                # 2. Recolectar inyecciones y delivery_meta calculados por los nodos en respuesta a este tick
                received_this_step = set()
                t_poll_limit = max(0.05, t_next - time.perf_counter())
                max_wait = 0.25 if step == 1 else (0.10 if self.fast_mode else min(t_poll_limit, 0.42))
                poll_deadline = time.perf_counter() + max_wait

                while time.perf_counter() < poll_deadline:
                    time_left_ms = max(1, int((poll_deadline - time.perf_counter()) * 1000))
                    socks = dict(poller.poll(timeout=min(time_left_ms, 15)))
                    if self.master.rep_socket in socks and socks[self.master.rep_socket] == zmq.POLLIN:
                        try:
                            req_msg = self.master.rep_socket.recv_json()
                            node_id = req_msg.get("node_id")
                            if "injections" in req_msg:
                                injections.update(req_msg["injections"])
                                if "P_load_total_w" in req_msg:
                                    load_totals["P_load_total_w"] = float(req_msg["P_load_total_w"])
                                if "Q_load_total_var" in req_msg:
                                    load_totals["Q_load_total_var"] = float(req_msg["Q_load_total_var"])
                                sender_key = str(req_msg.get("source", "LOADS_RPi"))
                                seen_senders.add(sender_key)
                                received_this_step.add(sender_key)
                            elif node_id is not None:
                                n_int = int(node_id)
                                p_w = float(req_msg.get("P_w", 0.0))
                                q_v = float(req_msg.get("Q_var", 0.0))
                                injections[str(n_int)] = {"P": p_w, "Q": q_v}
                                meta_entry = {
                                    "P_w": p_w,
                                    "Q_var": q_v,
                                    "eta_excess": req_msg.get("eta_excess", 0.0),
                                    "curtail_ratio": req_msg.get("curtail_ratio", 1.0),
                                    "curtail_min": req_msg.get("curtail_min", 0.15),
                                    "P_curtailed": req_msg.get("P_curtailed", 0.0),
                                    "P_mpp": req_msg.get("P_mpp", p_w),
                                    "delivery_meta": req_msg.get("delivery_meta", {}),
                                }
                                if "SoC" in req_msg:
                                    meta_entry["SoC"] = req_msg["SoC"]
                                der_meta[n_int] = meta_entry
                                sender_key = f"N{n_int}"
                                seen_senders.add(sender_key)
                                received_this_step.add(sender_key)
                            last_injections = injections

                            # Responder inmediatamente al nodo que envio datos
                            self.master.rep_socket.send_json({"status": "ACK", "step": step})

                            # Salir tan pronto como todos los remitentes conocidos reporten este paso
                            if len(seen_senders) >= 4 and received_this_step >= seen_senders:
                                break
                        except Exception:
                            pass
                    else:
                        if len(seen_senders) >= 4 and received_this_step >= seen_senders:
                            break
                        if time.perf_counter() > poll_deadline - 0.015:
                            break

                total_cycle_ms = round((time.perf_counter() - step_wall_start) * 1000.0, 3)
                result["der_meta"] = {str(k): v for k, v in der_meta.items()}
                result["P_load_total_w"] = round(load_totals["P_load_total_w"], 2)
                result["Q_load_total_var"] = round(load_totals["Q_load_total_var"], 2)
                result["step_elapsed_ms"] = total_cycle_ms

                # Guardar respaldo local S-40 en el PC Central
                if self.backup_csv:
                    n_nodes = max([int(k) for k in result.get("voltages", {}).keys()], default=8)
                    if not csv_initialized:
                        with open(self.backup_csv, "w", newline="", encoding="utf-8") as f_bk:
                            csv.writer(f_bk).writerow(build_s40_headers(n_nodes))
                        csv_initialized = True
                    row_bk = build_s40_row(result, {}, num_nodes=n_nodes, v_base=self.v_base)
                    with open(self.backup_csv, "a", newline="", encoding="utf-8") as f_bk:
                        csv.writer(f_bk).writerow(row_bk)

                # Resumen en consola cada 2 pasos (1 vez por segundo)
                if step % 2 == 0 or step == max_steps:
                    v_nodes = result.get("voltages", {})
                    v_str = " | ".join([f"N{n}:{v['V_pu']:.4f}pu" for n, v in sorted(v_nodes.items(), key=lambda x: int(x[0]))])
                    f_sys = result.get("f_sys_hz", 60.0)
                    p_net = result.get("P_net_w", 0.0) / 1000.0
                    print(f"[{time.strftime('%H:%M:%S')}] Muestra {sample_idx:03d} (t={time_s:5.1f}s) | f={f_sys:.3f}Hz | P_net={p_net:6.2f}kW | cycle={total_cycle_ms:5.1f}ms | {v_str}")

                # Control preciso de deriva temporal
                if not self.fast_mode:
                    sleep_rem = t_next - time.perf_counter()
                    if sleep_rem > 0:
                        time.sleep(sleep_rem)

        except KeyboardInterrupt:
            print("\nDetencion solicitada por el usuario.")
        finally:
            self.master.close()
            print("Servidor ZMQ detenido.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servidor PC Central: Flujo de Potencia BT (400V) y Reloj ZMQ")
    parser.add_argument("--topology", default=os.path.join(os.path.dirname(__file__), "..", "config", "topologia_BT_6nodos.csv"))
    parser.add_argument("--v-base", type=float, default=400.0, help="Tension nominal base [V]")
    parser.add_argument("--s-base", type=float, default=10000.0, help="Potencia nominal base [VA]")
    parser.add_argument("--port-rep", type=int, default=5555, help="Puerto REP de inyecciones")
    parser.add_argument("--port-pub", type=int, default=5556, help="Puerto PUB de reloj y voltajes")
    parser.add_argument("--dt", type=float, default=0.5, help="Paso macro de reloj [s]")
    parser.add_argument("--steps", type=int, default=None, help="Numero maximo de pasos (None = infinito)")
    parser.add_argument("--backup-csv", default="output_data/telemetry_central_backup.csv", help="Ruta respaldo CSV central")
    parser.add_argument("--fast", action="store_true", help="Modo acelerado para simulacion SIL local sin esperar tiempo real")
    args = parser.parse_args()

    server = PowerFlowClockServer(
        topology_path=args.topology,
        v_base=args.v_base,
        s_base=args.s_base,
        port_rep=args.port_rep,
        port_pub=args.port_pub,
        step_dt=args.dt,
        backup_csv=args.backup_csv,
        fast_mode=args.fast
    )
    server.run(max_steps=args.steps)
