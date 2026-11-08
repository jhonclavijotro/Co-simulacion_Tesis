import sys
import os
import time
import math
import argparse
import json
from typing import Optional
import zmq

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Agents.node_dynamic_process import NodeDynamicProcess
from Agents.fixed_time_consensus import FixedTimeConsensusAgent


class DistributedNodeRunner:
    """
    Orquestador ejecutable de un Nodo DER Distribuido en hardware real (Raspberry Pi 5) o local.
    Integra:
      1. Dinámica física local (1 kHz integrado en micro-pasos a 500 ms con esquema Hold ZOH/FROH).
      2. Agente de Consenso Distribuido en Tiempo Fijo (FxTS) P2P entre Raspberry Pis.
      3. Sincronización y reporte de inyecciones (P, Q) mediante sockets ZeroMQ
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
        hold_mode: str = "ZOH",
        froh_lambda: float = 0.7,
        zfoh_lambda: Optional[float] = None,
        scenario_file: Optional[str] = None,
        v_base: float = 400.0,
        q_max: float = 10000.0,
        p_max: float = 20000.0,
        q_init: float = 0.0,
        p_init: float = 0.0,
        p_charge_max: float = 3000.0,
        p_min_diesel: float = 0.0,
        operating_mode: str = "OFFLINE"
    ):
        self.node_id = int(node_id)
        self.source_type = source_type.upper()
        self.master_host = master_host
        self.port_rep = port_rep
        self.port_pub = port_pub
        self.p2p_port = p2p_port
        self.neighbors_targets = neighbors or []  # List of "ip:port"

        # Cargar parámetros generales del escenario si se especifica archivo (S-24 S2)
        if scenario_file and os.path.exists(scenario_file):
            try:
                with open(scenario_file, "r", encoding="utf-8") as f:
                    scen_data = json.load(f)
                pg = scen_data.get("parametros_generales", {})
                if "hold_mode" in pg:
                    hold_mode = pg["hold_mode"]
                if "froh_lambda" in pg:
                    froh_lambda = float(pg["froh_lambda"])
                elif "zfoh_lambda" in pg:
                    froh_lambda = float(pg["zfoh_lambda"])
            except Exception as e:
                print(f"[AVISO] No se pudo leer {scenario_file}: {e}")

        h_mode = hold_mode.upper()
        self.hold_mode = "FROH" if h_mode == "ZFOH" else h_mode
        self.froh_lambda = float(zfoh_lambda if zfoh_lambda is not None else froh_lambda)
        self.zfoh_lambda = self.froh_lambda  # Alias retrocompatible

        self.v_base = float(v_base)
        self.q_max = float(q_max)
        self.p_max = float(p_max)
        self.q_init = float(q_init)
        self.p_init = float(p_init)
        self.p_charge_max = float(p_charge_max)
        self.p_min_diesel = float(p_min_diesel)
        self.curtail_ratio = 1.0
        self.eta_excess = 0.0
        self.operating_mode = operating_mode.upper()

        # Lazo Restaurativo PI de Frecuencia hacia Potencia Activa (Amortiguado y Asintótico)
        self.int_freq_error = 0.0
        self.k_p_freq = 250.0  # W/(rad/s)
        self.k_i_freq = 80.0   # W/(rad/s*s) - Restaura f a 60.0 Hz en 10-15s sin sobreimpulso

        # 1. Proceso de Dinamica Fisica (1 kHz) con ZOH por defecto unificado (S-24 S4, S5)
        self.dynamic_proc = NodeDynamicProcess(
            node_id=self.node_id,
            source_type=self.source_type,
            hold_mode=self.hold_mode,
            froh_lambda=self.froh_lambda
        )

        # 2. Agente de Consenso en Tiempo Fijo (FxTS)
        self.agent = FixedTimeConsensusAgent(
            agent_id=self.node_id,
            Q_max=self.q_max,
            P_max=self.p_max,
            mode=self.operating_mode,
            alpha=0.8,
            beta=1.2,
            c1=0.25,
            c2=0.15,
            epsilon=1e-3,
            max_stale_steps=4
        )
        # Inicializar ponderaciones de adyacencia derivando el ID del vecino a partir de su puerto ZMQ (node_id = puerto - 6000)
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
        self.Q_ref = float(self.q_init)
        self.P_ref = float(self.p_init)
        self.V_offset = 0.0       # Acumulador integrador de corrección de tensión [p.u.]
        self.omega_offset = 0.0   # Acumulador integrador de corrección de frecuencia [rad/s]

    def run(self, max_steps=None):
        print("=" * 65)
        print(f" NODO DISTRIBUIDO {self.node_id}: {self.source_type} ({self.operating_mode})")
        print(f" - Servidor Maestro:    {self.master_host}:{self.port_pub}")
        print(f" - Puerto P2P Local:    PUB :{self.p2p_port}")
        print(f" - Vecinos P2P:         {self.neighbors_targets}")
        print(f" - Reconstruccion Hold: {self.hold_mode} (lambda={self.froh_lambda})")
        print(f" - Limites Capacidad:   P_max={self.p_max/1000:.0f}kW, Q_max={self.q_max/1000:.0f}kvar")
        print("=" * 65)
        print("Esperando sincronizacion del PC Central...\n")

        self.running = True
        step_count = 0
        neighbor_cache = {}

        try:
            while self.running:
                # 1. Esperar tick de reloj y tensiones del PC Central
                try:
                    clock_msg = self.sub_clock.recv_json()
                except zmq.Again:
                    print("[AVISO] Esperando sincronizacion del PC Central...")
                    continue

                step_count += 1
                if max_steps and step_count > max_steps:
                    break

                step_idx = clock_msg.get("step", step_count)
                time_s = clock_msg.get("time_sec", step_idx * 0.5)
                voltages = clock_msg.get("voltages", {})
                v_node_info = voltages.get(str(self.node_id), {})
                v_pcc_volts = v_node_info.get("V_volts", self.v_base)
                v_pcc_pu = v_node_info.get("V_pu", 1.0)
                f_sys = clock_msg.get("f_sys_hz", 60.0)

                # 2. Paso de Dinamica Fisica (1 kHz integrado a 500 ms)
                # Aplicar offset de tensión acumulado del consenso a la referencia del inversor
                v_pcc_corrected = v_pcc_volts + self.V_offset * self.v_base
                phys_out = self.dynamic_proc.step_macro(
                    V_pcc=v_pcc_corrected,
                    Q_ref=self.Q_ref,
                    P_ref=self.P_ref,
                    delta_omega=self.omega_offset,
                    curtail_ratio=self.curtail_ratio,
                    macro_dt=0.5,
                    micro_dt=0.001
                )
                P_w = phys_out["P_w"]
                Q_var = phys_out["Q_var"]
                soc = phys_out.get("SoC", None)
                p_curtailed = phys_out.get("P_curtailed", 0.0)

                # Actualizar índice de exceso local eta_excess in [0, 1] (S-36)
                if self.source_type == "BESS":
                    p_chg_cap = phys_out.get("P_charge_max", self.p_charge_max)
                    self.eta_excess = max(0.0, min(1.0, (-P_w) / p_chg_cap)) if (p_chg_cap > 0 and P_w < 0) else 0.0
                elif self.source_type == "SOLAR":
                    self.eta_excess = max(0.0, min(1.0, 1.0 - self.curtail_ratio))
                else:
                    self.eta_excess = 0.0

                # 3. Consenso P2P: Publicar estado local a los vecinos
                q_ratio = Q_var / self.q_max if self.q_max > 0 else 0.0
                p2p_payload = {
                    "sender_id": self.node_id,
                    "step": step_idx,
                    "V": v_pcc_pu,
                    "Q_ratio": q_ratio,
                    "omega": 2.0 * math.pi * f_sys,
                    "P_ratio": P_w / self.p_max if self.p_max > 0 else 0.0,
                    "eta_excess": round(self.eta_excess, 4),
                    "curtail_ratio": round(self.curtail_ratio, 4)
                }
                if soc is not None:
                    p2p_payload["SoC"] = round(float(soc), 4)
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
                                    "omega": msg_n.get("omega", 376.99),
                                    "P_ratio": msg_n.get("P_ratio", 0.0),
                                    "eta_excess": msg_n.get("eta_excess", 0.0),
                                    "curtail_ratio": msg_n.get("curtail_ratio", 1.0),
                                    "SoC": msg_n.get("SoC", None)
                                }
                        except Exception:
                            break
                    else:
                        break

                # 5. Actualizar ley de control FxTS
                omega_local = 2.0 * math.pi * f_sys
                dV, dQ, dw, dP = self.agent.update_consensus(
                    V_i=v_pcc_pu,
                    Q_i=Q_var,
                    omega_i=omega_local,
                    P_i=P_w,
                    eta_i=self.eta_excess,
                    neighbor_states=neighbor_cache,
                    dt=0.5,
                    return_all=True
                )
                self.Q_ref = max(-self.q_max, min(self.q_max, self.Q_ref + dQ))

                # Lazo de Control Secundario de Frecuencia y Reparto de Potencia Activa (Regimenes 1 y 2 / S-36)
                err_w = (2.0 * math.pi * 60.0) - omega_local
                if self.source_type == "DIESEL":
                    # Anti-windup acotado a [-75.0, +75.0] rad (hasta +/- 6.0 kW de compensacion integral)
                    self.int_freq_error = max(-75.0, min(75.0, self.int_freq_error + err_w * 0.5))
                    delta_P_restore = self.k_p_freq * err_w + self.k_i_freq * self.int_freq_error
                    base_p = self.p_init if self.p_init > 0 else 4000.0
                    self.P_ref = max(self.p_min_diesel, min(self.p_max, base_p + delta_P_restore + dP))
                elif self.source_type == "BESS":
                    # BESS bidireccional (descarga > 0 ante deficit, absorcion/carga < 0 ante sobrefrecuencia)
                    delta_P_droop = 40.0 * err_w
                    base_p = self.p_init if self.p_init != 0.0 else 0.0
                    p_target = base_p + delta_P_droop + dP
                    if err_w < -0.15:  # Sobrefrecuencia (f > 60.024 Hz, regimen excedentario)
                        d_eta_bess = self.agent.delta_eta
                        self.eta_excess = max(0.0, min(1.0, self.eta_excess + d_eta_bess - 0.02 * err_w))
                        p_charge_target = -self.eta_excess * self.p_charge_max
                        p_target = min(p_target, p_charge_target)
                    else:
                        self.eta_excess = max(0.0, min(1.0, self.eta_excess + self.agent.delta_eta - 0.02))
                    self.P_ref = max(-self.p_charge_max, min(self.p_max, p_target))
                elif self.source_type == "SOLAR":
                    # Solar: MPP nominal en equilibrio/deficit; curtailment coordinado ante sobrefrecuencia
                    if err_w < -0.15:  # Sobrefrecuencia (f > 60.024 Hz, regimen excedentario)
                        d_eta_pv = self.agent.delta_eta
                        self.eta_excess = max(0.0, min(1.0, self.eta_excess + d_eta_pv - 0.02 * err_w))
                        self.curtail_ratio = max(0.0, min(1.0, 1.0 - self.eta_excess))
                    else:
                        d_eta_pv = self.agent.delta_eta
                        self.eta_excess = max(0.0, min(1.0, self.eta_excess + d_eta_pv - 0.02))
                        self.curtail_ratio = max(0.0, min(1.0, 1.0 - self.eta_excess))
                    self.P_ref = max(0.0, min(self.p_max, self.P_ref))
                else:
                    self.P_ref = max(0.0, min(self.p_max, self.P_ref))

                # Acumular correcciones de tensión y frecuencia (acción integral del control secundario).
                self.V_offset = max(-0.10, min(0.10, self.V_offset + dV))
                self.omega_offset = max(-1.0, min(1.0, self.omega_offset + dw))

                # 6. Reportar inyeccion (P, Q) al PC Central
                inj_payload = {
                    "node_id": self.node_id,
                    "step": step_idx,
                    "P_w": round(P_w, 2),
                    "Q_var": round(Q_var, 2),
                    "eta_excess": round(self.eta_excess, 4),
                    "curtail_ratio": round(self.curtail_ratio, 4)
                }
                if soc is not None:
                    inj_payload["SoC"] = round(float(soc), 4)
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
                    extra_info = f" | SoC={soc:.3f}" if soc is not None else (f" | curtail={(1.0-self.curtail_ratio)*100:.1f}%" if self.source_type == "SOLAR" else "")
                    print(f"[{self.source_type} N{self.node_id}] Paso {step_idx:04d} (t={time_s:5.1f}s) | V={v_pcc_pu:.4f}pu (\u03b4V={self.V_offset:+.4f}) | f={f_sys:.2f}Hz (\u03b4\u03c9={self.omega_offset:+.3f}) | P={P_w/1000:6.1f}kW | Q={Q_var/1000:5.1f}kvar | dQ={dQ:+.1f}{extra_info}")

        except KeyboardInterrupt:
            print(f"\nDeteniendo nodo {self.node_id}...")
        finally:
            self.close()
            print(f"Nodo {self.node_id} finalizado.")

    def close(self):
        """Cierra sockets y libera el contexto ZeroMQ limpiamente."""
        try:
            self.sub_clock.close(linger=0)
            self.req_master.close(linger=0)
            self.pub_p2p.close(linger=0)
            self.sub_p2p.close(linger=0)
            self.context.term()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ejecutor de Nodo Distribuido DER")
    parser.add_argument("--node-id", type=int, required=True, help="ID del nodo (1=Diesel, 2=Solar, 3=BESS)")
    parser.add_argument("--source-type", required=True, choices=["DIESEL", "SOLAR", "BESS"], help="Tipo de fuente DER")
    parser.add_argument("--master-host", default="10.0.0.156", help="IP del PC Central")
    parser.add_argument("--port-rep", type=int, default=5555, help="Puerto REP de inyecciones")
    parser.add_argument("--port-pub", type=int, default=5556, help="Puerto PUB del reloj")
    parser.add_argument("--p2p-port", type=int, default=6000, help="Puerto PUB local para consenso P2P")
    parser.add_argument("--neighbors", nargs="*", default=[], help="Lista de vecinos en formato ip:puerto")
    parser.add_argument("--hold-mode", default="ZOH", choices=["ZOH", "FOH", "FROH", "ZFOH"], help="Esquema Hold (ZOH canónico por defecto, FOH, FROH)")
    parser.add_argument("--froh-lambda", type=float, default=0.7, help="Parámetro lambda FROH")
    parser.add_argument("--lambda-val", type=float, default=None, help="Alias retrocompatible de lambda")
    parser.add_argument("--zfoh-lambda", type=float, default=None, help="Alias retrocompatible de lambda ZFOH")
    parser.add_argument("--scenario-file", default=None, help="Ruta al archivo JSON de configuración del escenario (prevalece sobre defaults)")
    parser.add_argument("--v-base", type=float, default=400.0, help="Tension base nominal [V]")
    parser.add_argument("--q-max", type=float, default=10000.0, help="Capacidad reactiva maxima [var]")
    parser.add_argument("--p-max", type=float, default=20000.0, help="Capacidad activa maxima [W]")
    parser.add_argument("--q-init", type=float, default=0.0, help="Consigna inicial de reactiva [var]")
    parser.add_argument("--p-init", type=float, default=0.0, help="Consigna inicial de activa [W]")
    parser.add_argument("--p-charge-max", type=float, default=3000.0, help="Capacidad maxima de absorcion/carga BESS [W]")
    parser.add_argument("--p-min-diesel", type=float, default=0.0, help="Potencia minima tecnica del generador diesel [W]")
    parser.add_argument("--mode", default="OFFLINE", choices=["ONLINE", "OFFLINE"], help="Modo de operacion")
    parser.add_argument("--steps", type=int, default=None, help="Numero maximo de pasos")
    args = parser.parse_args()

    # Resolver alias de lambda
    active_lambda = args.froh_lambda
    if args.lambda_val is not None:
        active_lambda = args.lambda_val
    elif args.zfoh_lambda is not None:
        active_lambda = args.zfoh_lambda

    runner = DistributedNodeRunner(
        node_id=args.node_id,
        source_type=args.source_type,
        master_host=args.master_host,
        port_rep=args.port_rep,
        port_pub=args.port_pub,
        p2p_port=args.p2p_port,
        neighbors=args.neighbors,
        hold_mode=args.hold_mode,
        froh_lambda=active_lambda,
        scenario_file=args.scenario_file,
        v_base=args.v_base,
        q_max=args.q_max,
        p_max=args.p_max,
        q_init=args.q_init,
        p_init=args.p_init,
        p_charge_max=args.p_charge_max,
        p_min_diesel=args.p_min_diesel,
        operating_mode=args.mode
    )
    runner.run(max_steps=args.steps)
