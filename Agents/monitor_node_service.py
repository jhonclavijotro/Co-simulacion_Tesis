import sys
import os
import time
import argparse
import csv
import json
import zmq


def build_s40_headers(num_nodes: int = 8) -> list:
    """Construye la cabecera unificada S-40 para telemetría de Monitor y PC Central."""
    headers = ["step", "time_sec", "time_s", "f_sys_hz", "P_net_W", "P_net_kW"]
    headers += [f"V{i}_pu" for i in range(1, num_nodes + 1)]
    headers += [f"V{i}_V" for i in range(1, num_nodes + 1)]
    headers += [
        "P1_kW", "P2_kW", "P3_kW", "P_load_total_kW",
        "Q1_kvar", "Q2_kvar", "Q3_kvar",
        "SoC", "curtail_ratio", "curtail_min", "P_curtailed_kW",
        "Q_ratio_1", "Q_ratio_2", "Q_ratio_3",
        "error_Q_12", "error_Q_23", "error_V_12", "error_V_23",
        "e_Q", "e_P", "e_V", "e_f",
        "falla_activa", "contingencias_activas", "perdida_efectiva",
        "paquetes_intentados", "paquetes_entregados", "paquetes_descartados",
        "step_elapsed_ms",
    ]
    return headers


def build_s40_row(
    clock_msg: dict,
    der_states: dict,
    num_nodes: int = 8,
    v_base: float = 400.0,
) -> list:
    """Construye una fila normalizada S-40 combinando el broadcast maestro y metadatos DER."""
    raw_step = int(clock_msg.get("step", 1))
    sample_idx = int(clock_msg.get("sample_idx", max(0, raw_step - 1)))
    time_s = float(clock_msg.get("time_s", round(sample_idx * 0.5, 2)))
    f_sys = float(clock_msg.get("f_sys_hz", 60.0))
    p_net_w = float(clock_msg.get("P_net_w", 0.0))
    p_net_kw = p_net_w / 1000.0
    voltages = clock_msg.get("voltages", {})
    inj_eff = clock_msg.get("injections_effective", {})
    der_meta_clock = clock_msg.get("der_meta", {})

    merged_ders = {}
    for nid in (1, 2, 3):
        info = {}
        c_info = der_meta_clock.get(str(nid)) or der_meta_clock.get(nid)
        if isinstance(c_info, dict):
            info.update(c_info)
        d_live = der_states.get(nid) or der_states.get(str(nid))
        if isinstance(d_live, dict):
            for k, v in d_live.items():
                if v is not None:
                    info[k] = v
        merged_ders[nid] = info

    v_pu = [float((voltages.get(str(i)) or voltages.get(i) or {}).get("V_pu", 1.0)) for i in range(1, num_nodes + 1)]
    v_volts = [float((voltages.get(str(i)) or voltages.get(i) or {}).get("V_volts", v_base)) for i in range(1, num_nodes + 1)]

    def _der_pq(nid):
        d = merged_ders[nid]
        if "P_w" in d:
            p_w = float(d["P_w"])
        else:
            p_w = float((inj_eff.get(str(nid)) or inj_eff.get(nid) or {}).get("P", 0.0))
        if "Q_var" in d:
            q_v = float(d["Q_var"])
        else:
            q_v = float((inj_eff.get(str(nid)) or inj_eff.get(nid) or {}).get("Q", 0.0))
        return p_w, q_v

    p1_w, q1_v = _der_pq(1)
    p2_w, q2_v = _der_pq(2)
    p3_w, q3_v = _der_pq(3)

    if "P_load_total_w" in clock_msg:
        p_load_total_kw = float(clock_msg["P_load_total_w"]) / 1000.0
    else:
        p_load_total_kw = sum(
            max(0.0, -float((inj_eff.get(str(n)) or inj_eff.get(n) or {}).get("P", 0.0)))
            for n in range(4, num_nodes + 1)
        ) / 1000.0

    soc_val = merged_ders[3].get("SoC", "")
    soc_out = round(float(soc_val), 6) if soc_val not in ("", None) else ""
    curtail_val = float(merged_ders[2].get("curtail_ratio", 1.0))
    curtail_min_val = float(merged_ders[2].get("curtail_min", 0.15))
    p_curtailed_kw = float(merged_ders[2].get("P_curtailed", 0.0)) / 1000.0

    q_caps = {1: 6000.0, 2: 3000.0, 3: 2000.0}
    p_caps = {1: 10000.0, 2: 5000.0, 3: 3000.0}
    q_ratio_1 = float(merged_ders[1].get("Q_ratio", q1_v / q_caps[1]))
    q_ratio_2 = float(merged_ders[2].get("Q_ratio", q2_v / q_caps[2]))
    q_ratio_3 = float(merged_ders[3].get("Q_ratio", q3_v / q_caps[3]))

    p_ratio_1 = float(merged_ders[1].get("P_ratio", p1_w / p_caps[1]))
    p_ratio_2 = float(merged_ders[2].get("P_ratio", p2_w / p_caps[2]))
    p_ratio_3 = float(merged_ders[3].get("P_ratio", p3_w / p_caps[3]))

    err_q_12 = abs(q_ratio_1 - q_ratio_2)
    err_q_23 = abs(q_ratio_2 - q_ratio_3)
    err_v_12 = abs(v_pu[0] - v_pu[1]) if len(v_pu) >= 2 else 0.0
    err_v_23 = abs(v_pu[1] - v_pu[2]) if len(v_pu) >= 3 else 0.0

    e_q = max(err_q_12, err_q_23)
    e_p = max(abs(p_ratio_1 - p_ratio_2), abs(p_ratio_2 - p_ratio_3))
    e_v = max(err_v_12, err_v_23)
    e_f = abs(f_sys - 60.0)

    # Agregación de contingencias y entregas telemáticas P2P
    falla_activa = 0
    cont_set = set()
    attempted = 0
    delivered = 0
    dropped = 0
    for nid in (1, 2, 3):
        dm = merged_ders[nid].get("delivery_meta") or {}
        if isinstance(dm, dict) and dm:
            if dm.get("falla_activa"):
                falla_activa = 1
            for cid in dm.get("active_contingencies", []):
                cont_set.add(str(cid))
            attempted += int(dm.get("attempted", 0))
            delivered += int(dm.get("delivered", 0))
            dropped += int(dm.get("dropped", 0))

    contingencias_str = ";".join(sorted(cont_set)) if cont_set else "NONE"
    perdida_efectiva = round(dropped / attempted, 4) if attempted > 0 else 0.0
    step_elapsed_ms = float(clock_msg.get("step_elapsed_ms", 0.0))

    return [
        sample_idx,
        round(time_s, 2),
        round(time_s, 2),
        round(f_sys, 4),
        round(p_net_w, 2),
        round(p_net_kw, 4),
        *[round(x, 5) for x in v_pu],
        *[round(x, 2) for x in v_volts],
        round(p1_w / 1000.0, 4),
        round(p2_w / 1000.0, 4),
        round(p3_w / 1000.0, 4),
        round(p_load_total_kw, 4),
        round(q1_v / 1000.0, 4),
        round(q2_v / 1000.0, 4),
        round(q3_v / 1000.0, 4),
        soc_out,
        round(curtail_val, 4),
        round(curtail_min_val, 4),
        round(p_curtailed_kw, 4),
        round(q_ratio_1, 4),
        round(q_ratio_2, 4),
        round(q_ratio_3, 4),
        round(err_q_12, 4),
        round(err_q_23, 4),
        round(err_v_12, 5),
        round(err_v_23, 5),
        round(e_q, 4),
        round(e_p, 4),
        round(e_v, 5),
        round(e_f, 4),
        falla_activa,
        contingencias_str,
        perdida_efectiva,
        attempted,
        delivered,
        dropped,
        round(step_elapsed_ms, 3),
    ]

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
        headers = build_s40_headers(n_count)
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

                # Recoger ultimos paquetes de los DERs en la red (STATE + DELIVERY_META del paso actual)
                meta_ready = set()
                poll_end = time.perf_counter() + 0.065
                while time.perf_counter() < poll_end:
                    socks = dict(self.poller.poll(timeout=8))
                    if self.sub_ders in socks and socks[self.sub_ders] == zmq.POLLIN:
                        try:
                            der_msg = self.sub_ders.recv_json()
                            s_id = der_msg.get("sender_id")
                            if s_id is not None:
                                s_int = int(s_id)
                                if der_msg.get("msg_type") == "DELIVERY_META":
                                    der_states.setdefault(s_int, {})["delivery_meta"] = der_msg.get("delivery_meta", {})
                                    if der_msg.get("step") == step_idx:
                                        meta_ready.add(s_int)
                                else:
                                    prev_dm = der_states.get(s_int, {}).get("delivery_meta")
                                    der_states[s_int] = der_msg
                                    if prev_dm and "delivery_meta" not in der_msg:
                                        der_states[s_int]["delivery_meta"] = prev_dm
                            if len(meta_ready) >= 3:
                                break
                        except Exception:
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

                # Escribir fila unificada S-40 en CSV
                row = build_s40_row(clock_msg, der_states, num_nodes=self.num_nodes, v_base=self.v_base)
                with open(self.output_csv, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(row)

                if step_idx % 2 == 0:
                    v_min = min(v_pu) if v_pu else 1.0
                    v_max = max(v_pu) if v_pu else 1.0
                    print(f"[MONITOR] Paso {step_idx:04d} (t={clock_msg.get('time_s', time_s):.1f}s) | f={f_sys:.3f}Hz | P_net={p_net:5.1f}kW | Err_Q(1-2)={err_q_12:.4f} | Err_Q(2-3)={err_q_23:.4f} | V_min={v_min:.4f}pu | V_max={v_max:.4f}pu")

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
