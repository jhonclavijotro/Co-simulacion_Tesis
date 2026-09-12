import sys
import os
import time
import socket
import json
import argparse
import signal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Central_PC.master_clock_zmq import MasterClockZMQ

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
    - Ejecuta el Flujo de Potencia Radial MT (FBS) a 13.8 kV.
    - Sincroniza el Reloj Maestro ZeroMQ a 500 ms (2 Hz).
    - Opera en Modo Isla (OFFLINE) con Nodo 1 (Diésel) como barra Slack.
    """
    def __init__(
        self,
        topology_path: str,
        v_base: float = 13800.0,
        s_base: float = 1000000.0,
        port_rep: int = 5555,
        port_pub: int = 5556,
        step_dt: float = 0.5,
        operating_mode: str = "OFFLINE"
    ):
        self.topology_path = topology_path
        self.v_base = float(v_base)
        self.s_base = float(s_base)
        self.port_rep = port_rep
        self.port_pub = port_pub
        self.step_dt = float(step_dt)
        self.operating_mode = operating_mode.upper()
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
        self.master.set_operating_mode(self.operating_mode, slack_node=1, V_slack=1.0)
        self.running = False

    def run(self, max_steps: int = None):
        print("=" * 65)
        print(" SERVIDOR CENTRAL PC: SOLVER MT (13.8 kV) & RELOJ MAESTRO ZMQ")
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
        t_next = time.perf_counter()

        import zmq
        poller = zmq.Poller()
        poller.register(self.master.rep_socket, zmq.POLLIN)

        try:
            while self.running:
                step += 1
                if max_steps and step > max_steps:
                    break

                t_next += self.step_dt

                # Recolectar inyecciones enviadas por las Raspberry Pis
                injections = dict(last_injections)
                t_poll_limit = max(0.01, t_next - time.perf_counter())
                poll_timeout_ms = int(t_poll_limit * 1000)

                socks = dict(poller.poll(timeout=min(poll_timeout_ms, 450)))
                if self.master.rep_socket in socks and socks[self.master.rep_socket] == zmq.POLLIN:
                    try:
                        req_msg = self.master.rep_socket.recv_json()
                        node_id = req_msg.get("node_id")
                        if "injections" in req_msg:
                            injections.update(req_msg["injections"])
                        elif node_id is not None:
                            injections[str(node_id)] = {
                                "P": float(req_msg.get("P_w", 0.0)),
                                "Q": float(req_msg.get("Q_var", 0.0))
                            }
                        last_injections = injections

                        # Responder inmediatamente al nodo que envio datos
                        self.master.rep_socket.send_json({"status": "ACK", "step": step})
                    except Exception as e:
                        pass

                # Resolver flujo de potencia FBS a 13.8 kV
                result = self.master.run_step(injections)

                # Resumen en consola cada 2 pasos (1 vez por segundo)
                if step % 2 == 0:
                    v_nodes = result.get("voltages", {})
                    v_str = " | ".join([f"N{n}:{v['V_pu']:.4f}pu" for n, v in sorted(v_nodes.items(), key=lambda x: int(x[0]))])
                    f_sys = result.get("f_sys_hz", 60.0)
                    p_net = result.get("P_net_w", 0.0) / 1000.0
                    print(f"[{time.strftime('%H:%M:%S')}] Paso {step:04d} (t={step*self.step_dt:5.1f}s) | f={f_sys:.3f}Hz | P_net={p_net:6.1f}kW | {v_str}")

                # Control preciso de deriva temporal
                sleep_rem = t_next - time.perf_counter()
                if sleep_rem > 0:
                    time.sleep(sleep_rem)

        except KeyboardInterrupt:
            print("\nDetencion solicitada por el usuario.")
        finally:
            self.master.close()
            print("Servidor ZMQ detenido.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servidor PC Central: Flujo de Potencia 13.8 kV y Reloj ZMQ")
    parser.add_argument("--topology", default=os.path.join(os.path.dirname(__file__), "..", "config", "topologia_MT_13_8kV_6nodos.csv"))
    parser.add_argument("--v-base", type=float, default=13800.0, help="Tension nominal base [V]")
    parser.add_argument("--s-base", type=float, default=1000000.0, help="Potencia nominal base [VA]")
    parser.add_argument("--port-rep", type=int, default=5555, help="Puerto REP de inyecciones")
    parser.add_argument("--port-pub", type=int, default=5556, help="Puerto PUB de reloj y voltajes")
    parser.add_argument("--dt", type=float, default=0.5, help="Paso macro de reloj [s]")
    parser.add_argument("--steps", type=int, default=None, help="Numero maximo de pasos (None = infinito)")
    args = parser.parse_args()

    server = PowerFlowClockServer(
        topology_path=args.topology,
        v_base=args.v_base,
        s_base=args.s_base,
        port_rep=args.port_rep,
        port_pub=args.port_pub,
        step_dt=args.dt
    )
    server.run(max_steps=args.steps)
