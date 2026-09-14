import sys
import os
import time
import math
import argparse
import json
import zmq

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Agents.node_dynamic_process import NodeDynamicProcess
from Agents.finite_time_consensus import FixedTimeConsensusAgent

class DistributedNodeRunner:
    """
    Ejecutor de Nodo Distribuido para Raspberry Pi 5.
    Desacopla la Dinamica Fisica (1 kHz / micro-paso) y el Agente de Control Secundario (FxTS)
    intercambiando informacion P2P con nodos adyacentes sobre Ethernet y sincronizandose
    con el PC Central (Reloj Maestro ZMQ a 500 ms).
    """
    def __init__(
        self,
        node_id: int,
        source_type: str,
        master_host: str = "10.0.0.156",
        port_rep: int = 5555,
        port_pub: int = 5556,
        p2p_port: int = 6000,
        neighbors: list = None,
        hold_mode: str = "ZFOH",
        zfoh_lambda: float = 0.7,
        v_base: float = 13800.0,
        q_max: float = 100000.0,
        p_max: float = 200000.0,
        operating_mode: str = "OFFLINE"
    ):
        self.node_id = int(node_id)
        self.source_type = source_type.upper()
        self.master_host = master_host
        self.port_rep = port_rep
        self.port_pub = port_pub
        self.p2p_port = p2p_port
        self.neighbors_targets = neighbors or []  # List of "ip:port"
        self.hold_mode = hold_mode.upper()
        self.zfoh_lambda = float(zfoh_lambda)
        self.v_base = float(v_base)
        self.q_max = float(q_max)
        self.p_max = float(p_max)
        self.operating_mode = operating_mode.upper()

        # 1. Proceso de Dinamica Fisica (1 kHz)
        self.dynamic_proc = NodeDynamicProcess(
            node_id=self.node_id,
            source_type=self.source_type,
            hold_mode=self.hold_mode,
            zfoh_lambda=self.zfoh_lambda
        )

        # 2. Agente de Consenso en Tiempo Fijo (FxTS)
        self.agent = FixedTimeConsensusAgent(
            agent_id=self.node_id,
            Q_max=self.q_max,
            P_max=self.p_max,
            mode=self.operating_mode,
            alpha=0.8,
            beta=1.2,
            c1=1.0,
            c2=1.0,
            epsilon=1e-3,
            max_stale_steps=4
        )
        # Matriz de adyacencia inicializada
        adj_init = {int(tgt.split(":")[-1]) - 6000: 1.0 for tgt in self.neighbors_targets if ":" in tgt}
        self.agent.set_adjacency(adj_init)

        # 3. Setup de Sockets ZeroMQ
        self.context = zmq.Context()

        # Socket SUB al PC Central (Reloj Maestro)
        self.sub_clock = self.context.socket(zmq.SUB)
        self.sub_clock.setsockopt(zmq.SUBSCRIBE, b"")
        self.sub_clock.setsockopt(zmq.RCVTIMEO, 3000)
        self.sub_clock.connect(f"tcp://{self.master_host}:{self.port_pub}")

        # Socket REQ al PC Central (Inyecciones P, Q)
        self.req_master = self.context.socket(zmq.REQ)
        self.req_master.setsockopt(zmq.RCVTIMEO, 2000)
        self.req_master.setsockopt(zmq.SNDTIMEO, 1000)
        self.req_master.connect(f"tcp://{self.master_host}:{self.port_rep}")

        # Socket PUB local para consenso P2P hacia vecinos
        self.pub_p2p = self.context.socket(zmq.PUB)
        self.pub_p2p.setsockopt(zmq.LINGER, 0)
        self.pub_p2p.bind(f"tcp://*:{self.p2p_port}")

        # Socket SUB hacia vecinos P2P
        self.sub_p2p = self.context.socket(zmq.SUB)
        self.sub_p2p.setsockopt(zmq.SUBSCRIBE, b"")
        self.sub_p2p.setsockopt(zmq.RCVTIMEO, 100)
        for target in self.neighbors_targets:
            self.sub_p2p.connect(f"tcp://{target}")

        self.poller_p2p = zmq.Poller()
        self.poller_p2p.register(self.sub_p2p, zmq.POLLIN)

        self.running = False
        self.Q_ref = 0.0
        self.P_ref = 0.0

    def run(self, max_steps=None):
        print("=" * 65)
        print(f" NODO DISTRIBUIDO {self.node_id}: {self.source_type} ({self.operating_mode})")
        print(f" - Servidor Maestro:    {self.master_host}:{self.port_pub}")
        print(f" - Puerto P2P Local:    PUB :{self.p2p_port}")
        print(f" - Vecinos P2P:         {self.neighbors_targets}")
        print(f" - Reconstruccion Hold: {self.hold_mode} (lambda={self.zfoh_lambda})")
        print(f" - Limites Capacidad:   P_max={self.p_max/1000:.0f}kW, Q_max={self.q_max/1000:.0f}kvar")
        print("=" * 65)
        print("Esperando sincronizacion del PC Central...\n")

        self.running = True
        step_count = 0
        neighbor_cache = {}

        try:
            while self.running:
                step_count += 1
                if max_steps and step_count > max_steps:
                    break

                # 1. Esperar tick de reloj y tensiones del PC Central
                try:
                    clock_msg = self.sub_clock.recv_json()
                except zmq.Again:
                    print("[AVISO] Esperando sincronizacion del PC Central...")
                    continue

                step_idx = clock_msg.get("step", step_count)
                time_s = clock_msg.get("time_sec", step_idx * 0.5)
                voltages = clock_msg.get("voltages", {})
                v_node_info = voltages.get(str(self.node_id), {})
                v_pcc_volts = v_node_info.get("V_volts", self.v_base)
                v_pcc_pu = v_node_info.get("V_pu", 1.0)
                f_sys = clock_msg.get("f_sys_hz", 60.0)

                # 2. Paso de Dinamica Fisica (1 kHz integrado a 500 ms)
                phys_out = self.dynamic_proc.step_macro(
                    V_pcc=v_pcc_volts,
                    Q_ref=self.Q_ref,
                    P_ref=self.P_ref,
                    macro_dt=0.5,
                    micro_dt=0.001
                )
                P_w = phys_out["P_w"]
                Q_var = phys_out["Q_var"]

                # 3. Consenso P2P: Publicar estado local a los vecinos
                q_ratio = Q_var / self.q_max if self.q_max > 0 else 0.0
                p2p_payload = {
                    "sender_id": self.node_id,
                    "step": step_idx,
                    "V": v_pcc_pu,
                    "Q_ratio": q_ratio,
                    "omega": 2.0 * math.pi * f_sys,
                    "P_ratio": P_w / self.p_max if self.p_max > 0 else 0.0
                }
                self.pub_p2p.send_json(p2p_payload)

                # 4. Consenso P2P: Recoger estados de los vecinos
                time.sleep(0.01)  # Breve margen de 10ms para transito de paquetes en switch
                while True:
                    socks = dict(self.poller_p2p.poll(timeout=10))
                    if self.sub_p2p in socks and socks[self.sub_p2p] == zmq.POLLIN:
                        try:
                            msg_n = self.sub_p2p.recv_json()
                            s_id = msg_n.get("sender_id")
                            if s_id is not None:
                                neighbor_cache[int(s_id)] = {
                                    "V": msg_n.get("V", 1.0),
                                    "Q_ratio": msg_n.get("Q_ratio", 0.0),
                                    "omega": msg_n.get("omega", 376.99)
                                }
                        except Exception:
                            break
                    else:
                        break

                # 5. Actualizar ley de control FxTS
                dV, dQ, dw, dP = self.agent.update_consensus(
                    V_i=v_pcc_pu,
                    Q_i=Q_var,
                    neighbor_states=neighbor_cache,
                    dt=0.5,
                    return_all=True
                )
                self.Q_ref = max(-self.q_max, min(self.q_max, self.Q_ref + dQ))
                self.P_ref = max(0.0, min(self.p_max, self.P_ref + dP))

                # 6. Reportar inyeccion (P, Q) al PC Central
                inj_payload = {
                    "node_id": self.node_id,
                    "step": step_idx,
                    "P_w": round(P_w, 2),
                    "Q_var": round(Q_var, 2)
                }
                try:
                    self.req_master.send_json(inj_payload)
                    ack = self.req_master.recv_json()
                except Exception as e:
                    try:
                        self.req_master.close(linger=0)
                    except Exception:
                        pass
                    self.req_master = self.context.socket(zmq.REQ)
                    self.req_master.setsockopt(zmq.RCVTIMEO, 500)
                    self.req_master.setsockopt(zmq.SNDTIMEO, 500)
                    self.req_master.connect(f"tcp://{self.master_host}:{self.port_rep}")

                # Resumen en consola cada 2 pasos (1 vez por segundo)
                if step_idx % 2 == 0:
                    print(f"[{self.source_type} N{self.node_id}] Paso {step_idx:04d} (t={time_s:5.1f}s) | V={v_pcc_pu:.4f}pu ({v_pcc_volts:.1f}V) | P={P_w/1000:6.1f}kW | Q={Q_var/1000:5.1f}kvar (Ratio={q_ratio:.3f}) | dQ={dQ:+.1f}")

        except KeyboardInterrupt:
            print(f"\nDeteniendo nodo {self.node_id}...")
        finally:
            self.sub_clock.close()
            self.req_master.close()
            self.pub_p2p.close()
            self.sub_p2p.close()
            self.context.term()
            print(f"Nodo {self.node_id} finalizado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ejecutor de Nodo Distribuido DER")
    parser.add_argument("--node-id", type=int, required=True, help="ID del nodo (1=Diesel, 2=Solar, 3=BESS)")
    parser.add_argument("--source-type", required=True, choices=["DIESEL", "SOLAR", "BESS"], help="Tipo de fuente DER")
    parser.add_argument("--master-host", default="10.0.0.156", help="IP del PC Central")
    parser.add_argument("--port-rep", type=int, default=5555, help="Puerto REP de inyecciones")
    parser.add_argument("--port-pub", type=int, default=5556, help="Puerto PUB del reloj")
    parser.add_argument("--p2p-port", type=int, default=6000, help="Puerto PUB local para consenso P2P")
    parser.add_argument("--neighbors", nargs="*", default=[], help="Lista de vecinos en formato ip:puerto")
    parser.add_argument("--hold-mode", default="ZFOH", choices=["ZOH", "FOH", "ZFOH"], help="Esquema Hold")
    parser.add_argument("--lambda-val", type=float, default=0.7, help="Parametro lambda ZFOH")
    parser.add_argument("--q-max", type=float, default=100000.0, help="Capacidad reactiva maxima [var]")
    parser.add_argument("--p-max", type=float, default=200000.0, help="Capacidad activa maxima [W]")
    parser.add_argument("--mode", default="OFFLINE", choices=["ONLINE", "OFFLINE"], help="Modo de operacion")
    parser.add_argument("--steps", type=int, default=None, help="Numero maximo de pasos")
    args = parser.parse_args()

    runner = DistributedNodeRunner(
        node_id=args.node_id,
        source_type=args.source_type,
        master_host=args.master_host,
        port_rep=args.port_rep,
        port_pub=args.port_pub,
        p2p_port=args.p2p_port,
        neighbors=args.neighbors,
        hold_mode=args.hold_mode,
        zfoh_lambda=args.lambda_val,
        q_max=args.q_max,
        p_max=args.p_max,
        operating_mode=args.mode
    )
    runner.run(max_steps=args.steps)
