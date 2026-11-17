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
from Agents.network_impairment_proxy import NetworkImpairmentProxy


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
        p_min_diesel: Optional[float] = None,
        curtail_min: Optional[float] = None,
        operating_mode: str = "OFFLINE",
        network_profile: str = "IDEAL",
        contingencies_file: Optional[str] = None,
        network_seed: int = 42,
        q_perturb_node: Optional[int] = None,
        q_perturb_var: float = 0.0,
        q_perturb_start: float = 40.0,
        q_perturb_end: float = 120.0,
        m_q: Optional[float] = None,
        diesel_integrator_deadband_hz: Optional[float] = None
    ):
        self.node_id = int(node_id)
        self.source_type = source_type.upper()
        self.master_host = master_host
        self.port_rep = port_rep
        self.port_pub = port_pub
        self.p2p_port = p2p_port
        self.neighbors_targets = neighbors or []  # List of "ip:port"
        self.network_profile = network_profile.upper()
        self.contingencies_file = contingencies_file
        self.network_seed = int(network_seed)

        escenario_dir = self._resolve_active_scenario_dir()
        meta_data = {}
        if escenario_dir:
            meta_path = os.path.join(escenario_dir, "meta.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f_meta:
                        meta_data = json.load(f_meta)
                except Exception:
                    pass
            if not scenario_file:
                cand_scen = os.path.join(escenario_dir, "plantilla_configuracion_cosimulacion.json")
                if os.path.exists(cand_scen):
                    scenario_file = cand_scen

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
                ec = scen_data.get("emulador_canal", {})
                if "escenario" in ec and self.network_profile == "IDEAL":
                    self.network_profile = ec["escenario"].upper()
                if not self.contingencies_file and "contingencias" in scen_data:
                    c_path = os.path.join(os.path.dirname(scenario_file), scen_data["contingencias"])
                    if os.path.exists(c_path):
                        self.contingencies_file = c_path
                # Soporte para perturbaciones directas en DERs (S-O-30 / D-31)
                der_events = scen_data.get("eventos_der") or scen_data.get("perturbaciones_der") or []
                for ev in der_events:
                    if int(ev.get("nodo", 0)) == self.node_id:
                        q_perturb_node = self.node_id
                        q_perturb_var = float(ev.get("delta_Q_var", ev.get("delta_q_var", ev.get("valor_var", 0.0))))
                        q_perturb_start = float(ev.get("inicio_s", ev.get("tiempo_s", 40.0)))
                        q_perturb_end = float(ev.get("fin_s", 120.0))
            except Exception as e:
                print(f"[AVISO] No se pudo leer {scenario_file}: {e}")

        # Resolver ruta de contingencias contra escenario activo si viene como nombre relativo
        if self.contingencies_file and not os.path.exists(self.contingencies_file) and escenario_dir:
            for cand in (
                os.path.join(escenario_dir, self.contingencies_file),
                os.path.join(escenario_dir, os.path.basename(self.contingencies_file)),
            ):
                if os.path.exists(cand):
                    self.contingencies_file = cand
                    break
        elif not self.contingencies_file and self.network_profile == "DYNAMIC_CONTINGENCY" and escenario_dir:
            cand_cont = os.path.join(escenario_dir, "contingencias_telematicas.csv")
            if os.path.exists(cand_cont):
                self.contingencies_file = cand_cont

        # Resolver piso técnico diésel y recorte solar desde meta.json si no se explicitó por CLI (S-O-25)
        reg_exc = meta_data.get("regimen_excedente") or {}
        if p_min_diesel is None:
            p_min_diesel = float(reg_exc.get("p_min_diesel_W", 0.0)) if self.source_type == "DIESEL" else 0.0
        if p_charge_max == 3000.0 and "p_charge_max_W" in reg_exc:
            p_charge_max = float(reg_exc["p_charge_max_W"])
        if curtail_min is None:
            curtail_min = float(reg_exc.get("curtail_min", 0.15))
        self.curtail_min = float(curtail_min)
        if diesel_integrator_deadband_hz is None:
            diesel_integrator_deadband_hz = float(reg_exc.get("diesel_integrator_deadband_hz", 0.030))
        self.diesel_integrator_deadband_hz = float(diesel_integrator_deadband_hz)

        # Gestor de perturbaciones telemáticas D-25 / S-34
        self.impairment_proxy = NetworkImpairmentProxy(
            profile=self.network_profile,
            seed=self.network_seed
        )
        if self.contingencies_file and os.path.exists(self.contingencies_file):
            try:
                self.impairment_proxy.load_contingencies_csv(self.contingencies_file, semilla_base=self.network_seed)
            except Exception as e:
                print(f"[AVISO] No se pudieron cargar contingencias telemáticas de {self.contingencies_file}: {e}")

        self.neighbor_cache = {}
        self.last_delivery_meta = {}

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
        # S-O-34 / C2: Máquina de estados para compuerta de recorte solar
        self.curtail_state = "IDLE"  # "IDLE" o "CURTAIL"
        self.curtail_dwell_steps = 0
        self.curtail_enter_steps = 0
        self.last_known_bess_soc = None
        self.operating_mode = operating_mode.upper()
        self.q_perturb_node = int(q_perturb_node) if q_perturb_node is not None else None
        self.q_perturb_var = float(q_perturb_var)
        self.q_perturb_start = float(q_perturb_start)
        self.q_perturb_end = float(q_perturb_end)

        # S-O-34 / C3: Droop Q-V unificado para hacer observable el reparto de reactiva
        # Caída a plena carga unificada a 8.0 V (2.0% de 400 V) => m_q = 8.0 / Q_max
        # N1 (Diésel): m_q = 0.00133 V/var (Q_max = 6 kvar)
        # N2 (Solar):  m_q = 0.00267 V/var (Q_max = 3 kvar)
        # N3 (BESS):   m_q = 0.00800 V/var (Q_max = 1 kvar)
        if m_q is not None and float(m_q) > 0.0:
            self.m_q = float(m_q)
        else:
            self.m_q = 8.0 / max(1.0, self.q_max)
        self.delta_Q_sec = 0.0
        self.q_slack_measured = None

        # Lazo Restaurativo PI de Frecuencia hacia Potencia Activa (Amortiguado y Asintótico)
        self.int_freq_error = 0.0
        self.k_p_freq = 1000.0  # W/(rad/s) - Droop primario diésel rápido (~6283 W/Hz)
        self.k_i_freq = 120.0   # W/(rad/s*s) - Acción integral para régimen permanente lento

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
        # Inicializar ponderaciones de adyacencia derivando el ID del vecino a partir de su puerto ZMQ (ej. 6001/16001 -> 1)
        adj_init = {int(tgt.split(":")[-1]) % 100: 1.0 for tgt in self.neighbors_targets if ":" in tgt}
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
        if self.source_type == "DIESEL" and self.p_min_diesel > 0.0 and self.P_ref < self.p_min_diesel:
            self.P_ref = self.p_min_diesel
        self.bess_p_int = float(self.P_ref) if self.source_type == "BESS" else 0.0
        self.V_offset = 0.0       # Acumulador integrador de corrección de tensión [p.u.]
        self.omega_offset = 0.0   # Acumulador integrador de corrección de frecuencia [rad/s]

    @staticmethod
    def _resolve_active_scenario_dir() -> Optional[str]:
        """Resuelve la carpeta del escenario activo leyendo Forms/escenarios_generados/ACTIVO.txt."""
        generados_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "Forms", "escenarios_generados")
        )
        marcador = os.path.join(generados_dir, "ACTIVO.txt")
        if not os.path.exists(marcador):
            return None
        try:
            with open(marcador, "r", encoding="utf-8") as f:
                nombre = f.read().lstrip("\ufeff").strip()
            if nombre:
                ruta = os.path.join(generados_dir, nombre)
                if os.path.isdir(ruta):
                    return ruta
        except OSError:
            pass
        return None

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
                sample_idx = max(0, int(step_idx) - 1)
                time_s = clock_msg.get("time_s", round(sample_idx * 0.5, 2))
                voltages = clock_msg.get("voltages", {})
                v_node_info = voltages.get(str(self.node_id), {})
                v_pcc_volts = v_node_info.get("V_volts", self.v_base)
                v_pcc_pu = v_node_info.get("V_pu", 1.0)
                f_sys = clock_msg.get("f_sys_hz", 60.0)

                # 2. Paso de Dinamica Fisica (1 kHz integrado a 500 ms)
                # S-O-34 / C3: Droop Q-V primario en función de la tensión en bornes (v_pcc_volts)
                # Caída a plena carga unificada a 8.0 V (2.0%) -> Q_droop = (V_nom - V_pcc) / m_q
                if self.source_type != "DIESEL":
                    q_droop = (self.v_base - v_pcc_volts) / self.m_q
                    self.Q_ref = max(0.0, min(self.q_max, q_droop + self.delta_Q_sec))

                # Aplicar offset de tensión acumulado del consenso a la referencia del inversor
                v_pcc_corrected = v_pcc_volts + self.V_offset * self.v_base
                # Perturbación reactiva local directa en DER (S-O-30 / D-31)
                delta_q_inj = 0.0
                if self.q_perturb_node == self.node_id and self.q_perturb_start <= time_s < self.q_perturb_end:
                    delta_q_inj = self.q_perturb_var
                effective_q_ref = max(-self.q_max, min(self.q_max, self.Q_ref + delta_q_inj))

                phys_out = self.dynamic_proc.step_macro(
                    V_pcc=v_pcc_corrected,
                    Q_ref=effective_q_ref,
                    P_ref=self.P_ref,
                    delta_omega=self.omega_offset,
                    curtail_ratio=self.curtail_ratio,
                    macro_dt=0.5,
                    micro_dt=0.001
                )
                P_w = phys_out["P_w"]
                Q_var = phys_out["Q_var"]
                # En modo isla, el Diésel asume la barra Slack física reportada por el solver
                if self.source_type == "DIESEL" and "Q_slack_var" in clock_msg:
                    self.q_slack_measured = float(clock_msg["Q_slack_var"])
                    Q_var = self.q_slack_measured
                soc = phys_out.get("SoC", None)
                p_curtailed = phys_out.get("P_curtailed", 0.0)
                p_mpp = phys_out.get("P_mpp", P_w)

                # 3. Consenso P2P: Publicar estado local a los vecinos (preservando self.eta_excess)
                q_ratio = Q_var / self.q_max if self.q_max > 0 else 0.0
                p2p_payload = {
                    "msg_type": "STATE",
                    "sender_id": self.node_id,
                    "step": step_idx,
                    "sample_idx": sample_idx,
                    "V": v_pcc_pu,
                    "Q_ratio": q_ratio,
                    "omega": 2.0 * math.pi * f_sys,
                    "P_w": round(P_w, 2),
                    "Q_var": round(Q_var, 2),
                    "P_ratio": P_w / self.p_max if self.p_max > 0 else 0.0,
                    "eta_excess": round(self.eta_excess, 4),
                    "curtail_ratio": round(self.curtail_ratio, 4),
                    "curtail_min": round(self.curtail_min, 4),
                    "P_curtailed": round(p_curtailed, 2),
                    "P_mpp": round(p_mpp, 2)
                }
                if soc is not None:
                    p2p_payload["SoC"] = round(float(soc), 6)
                self.pub_p2p.send_json(p2p_payload)

                # 4. Consenso P2P: Recoger estados de los vecinos (espera hasta 45ms o todos los vecinos)
                expected_neighbors = set(self.agent.adj_vector.keys())
                raw_neighbors = {}
                p2p_deadline = time.perf_counter() + 0.045
                while time.perf_counter() < p2p_deadline:
                    rem_ms = max(1, int((p2p_deadline - time.perf_counter()) * 1000))
                    socks = dict(self.poller_p2p.poll(timeout=min(rem_ms, 8)))
                    if self.sub_p2p in socks and socks[self.sub_p2p] == zmq.POLLIN:
                        try:
                            msg_n = self.sub_p2p.recv_json()
                            if msg_n.get("msg_type") == "DELIVERY_META":
                                continue
                            s_id = msg_n.get("sender_id")
                            if s_id is not None:
                                raw_neighbors[int(s_id)] = {
                                    "V": msg_n.get("V", 1.0),
                                    "Q_ratio": msg_n.get("Q_ratio", 0.0),
                                    "omega": msg_n.get("omega", 376.99),
                                    "P_ratio": msg_n.get("P_ratio", 0.0),
                                    "eta_excess": msg_n.get("eta_excess", 0.0),
                                    "curtail_ratio": msg_n.get("curtail_ratio", 1.0),
                                    "SoC": msg_n.get("SoC", None)
                                }
                            if expected_neighbors and set(raw_neighbors.keys()) >= expected_neighbors:
                                break
                        except Exception:
                            break
                    elif expected_neighbors and set(raw_neighbors.keys()) >= expected_neighbors:
                        break

                # Interceptar y perturbar canal mediante proxy de red (D-25 / S-34)
                filtered_neighbors, delivery_meta = self.impairment_proxy.filter_neighbor_states(
                    receiver_id=self.node_id,
                    raw_neighbor_states=raw_neighbors,
                    current_step=step_idx,
                    current_time_s=time_s
                )
                self.last_delivery_meta = delivery_meta
                self.pub_p2p.send_json({
                    "msg_type": "DELIVERY_META",
                    "sender_id": self.node_id,
                    "step": step_idx,
                    "sample_idx": sample_idx,
                    "delivery_meta": delivery_meta,
                })

                # 5. Actualizar ley de control FxTS con vecinos filtrados (disparando retención ZOH si hay pérdidas)
                omega_local = 2.0 * math.pi * f_sys
                dV, dQ, dw, dP = self.agent.update_consensus(
                    V_i=v_pcc_pu,
                    Q_i=Q_var,
                    omega_i=omega_local,
                    P_i=P_w,
                    eta_i=self.eta_excess,
                    neighbor_states=filtered_neighbors,
                    dt=0.5,
                    return_all=True
                )
                self.neighbor_cache = {n_id: data["state"] for n_id, data in self.agent.neighbor_buffer.items()}
                self.delta_Q_sec = max(-self.q_max, min(self.q_max, self.delta_Q_sec + dQ))
                if self.source_type != "DIESEL":
                    q_droop = (self.v_base - v_pcc_volts) / self.m_q
                    self.Q_ref = max(0.0, min(self.q_max, q_droop + self.delta_Q_sec))
                else:
                    self.Q_ref = max(-self.q_max, min(self.q_max, self.Q_ref + dQ))

                # Lazo de Control Secundario de Frecuencia y Reparto de Potencia Activa (Regimenes 1 y 2 / S-36 / D-28)
                df_hz = f_sys - 60.0
                err_w = (2.0 * math.pi * 60.0) - omega_local
                if self.source_type == "DIESEL":
                    # S-O-35 / C1: Banda muerta en el integrador secundario diésel (+-0.030 Hz / +-0.1885 rad/s)
                    # La acción integral solo acumula cuando |Delta f| > diesel_integrator_deadband_hz.
                    # Cuando |Delta f| <= diesel_integrator_deadband_hz, el integrador retiene su valor
                    # acumulado, permitiendo que el droop primario gobierne el equilibrio de régimen permanente.
                    deadband_w = 2.0 * math.pi * self.diesel_integrator_deadband_hz
                    if abs(err_w) > deadband_w:
                        self.int_freq_error = max(-75.0, min(75.0, self.int_freq_error + err_w * 0.5))
                    if self.p_min_diesel > 0.0 and self.P_ref <= self.p_min_diesel + 1.0 and self.int_freq_error < 0.0:
                        self.int_freq_error = max(-10.0, self.int_freq_error)
                    delta_P_restore = self.k_p_freq * err_w + self.k_i_freq * self.int_freq_error
                    base_p = self.p_init if self.p_init > 0 else max(4000.0, self.p_min_diesel)
                    self.P_ref = max(self.p_min_diesel, min(self.p_max, base_p + delta_P_restore + 0.1 * dP))

                    # Señalizar exceso cuando Diésel está en su piso técnico y persiste sobrefrecuencia
                    if self.p_min_diesel > 0.0 and self.P_ref <= self.p_min_diesel + 25.0 and df_hz > 0.015:
                        self.eta_excess = max(0.0, min(1.0, self.eta_excess + 0.3 * df_hz))
                    elif df_hz < -0.005 or self.P_ref > self.p_min_diesel + 100.0:
                        self.eta_excess = max(0.0, min(1.0, self.eta_excess - 0.03))

                elif self.source_type == "BESS":
                    # BESS bidireccional proporcional rápido (Droop primario P(f) desacoplado del integrador diésel)
                    p_chg_lim = min(self.p_charge_max, float(phys_out.get("P_charge_max", self.p_charge_max)))
                    p_dis_lim = min(self.p_max, float(phys_out.get("P_discharge_max", self.p_max)))

                    # S-O-34 / C1: Droop del BESS adaptativo por SoC
                    # m_p0 = 1.33e-4 Hz/W => k_p0 = 7500 W/Hz; banda de operación SoC [0.20, 0.80], k_SoC = 0.5
                    k_p0 = 7500.0
                    current_soc = float(soc) if soc is not None else 0.50
                    soc_clamped = max(0.20, min(0.80, current_soc))

                    if df_hz > 0.0:  # Carga (absorbiendo excedente de potencia activa)
                        # A menor SoC, mayor capacidad restante de carga => mayor ganancia
                        gain_factor = 1.0 + 0.5 * (0.50 - soc_clamped) / 0.30
                    else:  # Descarga (apoyando déficit de generación)
                        gain_factor = 1.0 + 0.5 * (soc_clamped - 0.50) / 0.30

                    k_p_eff = k_p0 * gain_factor

                    # Banda muerta de +-0.010 Hz para evitar chattering en régimen permanente
                    bess_deadband = 0.010
                    if abs(df_hz) > bess_deadband:
                        df_eff = df_hz - math.copysign(bess_deadband, df_hz)
                        p_target = -k_p_eff * df_eff
                    else:
                        p_target = 0.0
                    self.P_ref = max(-p_chg_lim, min(p_dis_lim, p_target))

                    # Coordinación de excedente eta_excess: BESS señaliza saturación real para consenso P2P
                    is_charging_saturated = (p_chg_lim <= 200.0) or (current_soc >= 0.90) or ((-P_w) >= 0.95 * p_chg_lim and p_chg_lim > 0.0)
                    if is_charging_saturated and df_hz > 0.015:
                        self.eta_excess = max(0.0, min(1.0, self.eta_excess + 0.3 * df_hz))
                    elif df_hz < -0.005 or ((-P_w) < 0.60 * p_chg_lim and current_soc < 0.85):
                        self.eta_excess = max(0.0, min(1.0, self.eta_excess - 0.03))
                    else:
                        self.eta_excess = max(0.0, min(1.0, self.eta_excess + 0.1 * self.agent.delta_eta))

                elif self.source_type == "SOLAR":
                    # Actualizar SoC conocido del BESS a través del canal P2P
                    for s in filtered_neighbors.values():
                        if "SoC" in s and s["SoC"] is not None:
                            self.last_known_bess_soc = float(s["SoC"])
                    bess_soc = self.last_known_bess_soc if self.last_known_bess_soc is not None else 0.50

                    # S-O-34 / C2: Compuerta de recorte por estado de carga con histéresis y reset del trinquete
                    # 1. Transición de IDLE a CURTAIL: f >= 60.060 Hz Y SoC >= 0.90 sostenido 2 s (4 pasos @ 0.5s)
                    if self.curtail_state == "IDLE":
                        if f_sys >= 60.060 and bess_soc >= 0.90:
                            self.curtail_enter_steps += 1
                            if self.curtail_enter_steps >= 4:  # 2.0 s sostenido
                                self.curtail_state = "CURTAIL"
                                self.curtail_dwell_steps = 0
                        else:
                            self.curtail_enter_steps = 0

                    # 2. Transición de CURTAIL a IDLE: f <= 60.040 Hz Y SoC <= 0.80 tras dwell mínimo de 2 s
                    elif self.curtail_state == "CURTAIL":
                        self.curtail_dwell_steps += 1
                        can_exit = (self.curtail_dwell_steps >= 4)
                        if can_exit and f_sys <= 60.040 and bess_soc <= 0.80:
                            self.curtail_state = "IDLE"
                            self.curtail_dwell_steps = 0
                            self.curtail_enter_steps = 0
                            # Reset del trinquete al volver a IDLE (C2)
                            self.eta_excess = 0.0
                            self.curtail_ratio = 1.0

                    # 3. Aplicar ley de control según el estado activo
                    if self.curtail_state == "CURTAIL":
                        # Ganancia de recorte k_f = 25 kW/Hz (recorte total a 0.20 Hz)
                        # Banda muerta / histéresis: base en 60.040 Hz
                        df_curtail = max(0.0, f_sys - 60.040)
                        p_curt_target = 25000.0 * df_curtail
                        p_mpp_ref = max(100.0, p_mpp if p_mpp > 0 else self.p_max)
                        eta_target = max(0.0, min(1.0, p_curt_target / p_mpp_ref))

                        # Filtrado suave de eta_excess para suprimir oscilaciones de alta frecuencia
                        self.eta_excess = max(0.0, min(1.0, self.eta_excess + 0.3 * (eta_target - self.eta_excess)))
                        self.curtail_ratio = max(self.curtail_min, min(1.0, 1.0 - self.eta_excess))
                    else:
                        # En estado IDLE: sin recorte (curtail_ratio = 1.0)
                        self.eta_excess = 0.0
                        self.curtail_ratio = 1.0

                    self.P_ref = max(0.0, min(self.p_max, self.P_ref))
                else:
                    self.P_ref = max(0.0, min(self.p_max, self.P_ref))

                # Acumular correcciones de tensión y frecuencia (acción integral del control secundario).
                self.V_offset = max(-0.10, min(0.10, self.V_offset + dV))
                self.omega_offset = max(-1.0, min(1.0, self.omega_offset + dw))

                # 6. Reportar inyeccion (P, Q) y telemetría S-40 al PC Central
                inj_payload = {
                    "node_id": self.node_id,
                    "step": step_idx,
                    "sample_idx": sample_idx,
                    "P_w": round(P_w, 2),
                    "Q_var": round(Q_var, 2),
                    "eta_excess": round(self.eta_excess, 4),
                    "curtail_ratio": round(self.curtail_ratio, 4),
                    "curtail_min": round(self.curtail_min, 4),
                    "P_curtailed": round(p_curtailed, 2),
                    "P_mpp": round(p_mpp, 2),
                    "delivery_meta": delivery_meta
                }
                if soc is not None:
                    inj_payload["SoC"] = round(float(soc), 6)
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
    parser.add_argument("--p-min-diesel", type=float, default=None, help="Potencia minima tecnica del generador diesel [W]")
    parser.add_argument("--curtail-min", type=float, default=None, help="Piso minimo de recorte solar (default: 0.15 o desde regimen_excedente en meta.json)")
    parser.add_argument("--mode", default="OFFLINE", choices=["ONLINE", "OFFLINE"], help="Modo de operacion")
    parser.add_argument("--network-profile", default="IDEAL", choices=["IDEAL", "DYNAMIC_CONTINGENCY", "LAN_ETHERNET", "INDUSTRIAL_WIFI", "SEVERE_STRESS", "CRITICAL_PARTITION", "CUSTOM"], help="Perfil de perturbaciones telemáticas")
    parser.add_argument("--contingencies-file", default=None, help="Ruta al archivo CSV de contingencias telemáticas D-25")
    parser.add_argument("--network-seed", type=int, default=42, help="Semilla pseudoaleatoria base de red (D-25)")
    parser.add_argument("--steps", type=int, default=None, help="Numero maximo de pasos")
    parser.add_argument("--q-perturb-node", type=int, default=None, help="Nodo DER para perturbacion reactiva (S-O-30)")
    parser.add_argument("--q-perturb-var", type=float, default=0.0, help="Magnitud de perturbacion reactiva [var]")
    parser.add_argument("--q-perturb-start", type=float, default=40.0, help="Inicio de perturbacion reactiva [s]")
    parser.add_argument("--q-perturb-end", type=float, default=120.0, help="Fin de perturbacion reactiva [s]")
    parser.add_argument("--m-q", type=float, default=None, help="Pendiente de droop Q-V en V/var (default: 8.0/Q_max)")
    parser.add_argument("--diesel-integrator-deadband-hz", type=float, default=None, help="Banda muerta del integrador secundario diésel en Hz (default: 0.030)")
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
        curtail_min=args.curtail_min,
        operating_mode=args.mode,
        network_profile=args.network_profile,
        contingencies_file=args.contingencies_file,
        network_seed=args.network_seed,
        q_perturb_node=args.q_perturb_node,
        q_perturb_var=args.q_perturb_var,
        q_perturb_start=args.q_perturb_start,
        q_perturb_end=args.q_perturb_end,
        m_q=args.m_q,
        diesel_integrator_deadband_hz=args.diesel_integrator_deadband_hz
    )
    runner.run(max_steps=args.steps)
