import zmq
import time
import json
import os
from Central_PC.power_flow_fbs import ForwardBackwardSweepSolver
from Central_PC.sensitivity_matrices import SensitivityMatrixSolver
from Central_PC.communication_emulator import CommunicationEmulator

class MasterClockZMQ:
    """
    Reloj Maestro y Orquestador de Co-simulación ZeroMQ para el PC Central.
    Sincroniza el tiempo maestro a 500 ms (2 Hz) y resuelve el flujo de potencia
    conmutando de forma explícita entre Modo FBS y Modo Sensibilidad (con selección de malla).

    Emulación de Canal de Comunicación:
      Integra un CommunicationEmulator opcional que introduce retardo variable
      y pérdida de paquetes para validar la robustez del algoritmo de consenso
      bajo condiciones reales de red (Objetivo 1 de la tesis).
    """
    def __init__(self, topology_csv, mode="FBS", mesh_type="RADIAL",
                 V_base=400.0, S_base=10000.0, port_rep=5555, port_pub=5556,
                 comm_scenario="IDEAL", comm_seed=None, max_hold_seconds=5.0):
        self.topology_csv = topology_csv
        self.mode = mode.upper()
        self.mesh_type = mesh_type.upper()
        self.V_base = V_base
        self.S_base = S_base
        self.port_rep = port_rep
        self.port_pub = port_pub
        self.max_hold_seconds = max_hold_seconds

        # Inicializar solucionador
        if self.mode == "FBS":
            self.solver = ForwardBackwardSweepSolver(V_base=V_base, S_base=S_base)
            self.solver.load_topology(topology_csv)
        elif self.mode == "SENSITIVITY":
            self.solver = SensitivityMatrixSolver(V_base=V_base, S_base=S_base, mesh_type=self.mesh_type)
            self.solver.load_topology(topology_csv)
        else:
            raise ValueError(f"Modo no reconocido: {mode}. Usar 'FBS' o 'SENSITIVITY'.")

        self.step_index = 0
        self.dt = 0.5  # 500 ms por paso maestro
        self.f_sys = 60.0
        self.f_nom = 60.0
        self.H_sys = 2.0
        self.D_sys = 1.0
        self.operating_mode = "ONLINE"

        # Emulador de Canal de Comunicación
        self.comm_emulator = CommunicationEmulator(scenario=comm_scenario, seed=comm_seed)

        # Seguimiento de frescura e inyecciones para política Hold Last Value / Disyuntor
        self.last_known_injections = {}
        self.node_stale_steps = {}
        self.tripped_nodes = set()

        # ZeroMQ Setup
        self.context = zmq.Context()
        self.rep_socket = self.context.socket(zmq.REP)
        self.rep_socket.setsockopt(zmq.LINGER, 0)
        self.rep_socket.setsockopt(zmq.RCVTIMEO, 2000)
        self.rep_socket.setsockopt(zmq.SNDTIMEO, 1000)
        self.rep_socket.bind(f"tcp://*:{self.port_rep}")

        self.pub_socket = self.context.socket(zmq.PUB)
        self.pub_socket.setsockopt(zmq.LINGER, 0)
        self.pub_socket.bind(f"tcp://*:{self.port_pub}")

        self.running = False

    def set_operating_mode(self, operating_mode: str, slack_node: int = 1, V_slack: float = 1.0):
        """
        Permite la transición ciber-física entre modos ONLINE y OFFLINE (isla).
        En modo FBS reconfigura la barra Slack correspondiente.
        """
        self.operating_mode = operating_mode.upper()
        if hasattr(self.solver, "set_operating_mode"):
            return self.solver.set_operating_mode(operating_mode, slack_node, V_slack)
        return self.operating_mode, slack_node, V_slack

    def run_step(self, node_injections):
        """
        Ejecuta un paso maestro de flujo de potencia con las inyecciones recolectadas.

        Si el emulador de comunicaciones está activo (escenario != IDEAL), introduce:
          1. Retardo variable (latencia/jitter) antes de procesar las inyecciones.
          2. Pérdida de paquetes: descarte aleatorio de inyecciones de nodo.

        Política de Retención (Hold Last Value) y Apertura de Disyuntor (> 5.0 s):
          - Si un paquete se pierde temporalmente (<= 5.0 s), se retiene la última inyección conocida.
          - Si la ausencia supera 5.0 s (> 10 macro-pasos), se asume apertura del disyuntor físico
            y se reduce la inyección nodal a P = 0.0 W, Q = 0.0 var.

        Parámetros:
            node_injections: {node_id: {"P": watts, "Q": vars}}

        Retorna:
            Dict con el payload de resultados del paso de simulación.
        """
        # Emular retardo de comunicación
        delay_applied = self.comm_emulator.apply_delay()

        # Emular pérdida de paquetes: filtrar inyecciones
        filtered_injections = self.comm_emulator.filter_injections(node_injections)

        # Actualizar o aplicar política de retención y apertura de disyuntor
        all_candidate_nodes = set(list(node_injections.keys()) + list(self.last_known_injections.keys()))
        effective_injections = {}
        stale_nodes = []

        for raw_node in all_candidate_nodes:
            n_int = int(raw_node)
            n_str = str(raw_node)

            if n_str in filtered_injections or n_int in filtered_injections:
                inj = filtered_injections.get(n_str, filtered_injections.get(n_int))
                self.last_known_injections[n_int] = {"P": float(inj["P"]), "Q": float(inj["Q"])}
                self.node_stale_steps[n_int] = 0
                self.tripped_nodes.discard(n_int)
                effective_injections[n_int] = self.last_known_injections[n_int]
            else:
                # Nodo no recibido en este paso (pérdida de paquete o nodo desconectado)
                stale_cnt = self.node_stale_steps.get(n_int, 0) + 1
                self.node_stale_steps[n_int] = stale_cnt
                stale_time = stale_cnt * self.dt

                if stale_time > self.max_hold_seconds:
                    # Apertura definitiva de disyuntor: potencia nula
                    self.tripped_nodes.add(n_int)
                    effective_injections[n_int] = {"P": 0.0, "Q": 0.0}
                else:
                    # Retener último valor conocido (Hold Last Value transitorio)
                    stale_nodes.append(n_int)
                    effective_injections[n_int] = self.last_known_injections.get(n_int, {"P": 0.0, "Q": 0.0})

        P_dict = {n: effective_injections[n]["P"] for n in effective_injections}
        Q_dict = {n: effective_injections[n]["Q"] for n in effective_injections}

        voltages_complex, conv, iters = self.solver.solve(P_dict, Q_dict)

        # Dinámica de frecuencia del sistema (Swing Equation en modo isla)
        if hasattr(self.solver, "compute_frequency_dynamics"):
            self.f_sys, p_net = self.solver.compute_frequency_dynamics(
                P_dict, f_prev=self.f_sys, dt=self.dt, H_sys=self.H_sys, D_sys=self.D_sys, f_nom=self.f_nom
            )
        else:
            p_net = sum(P_dict.values())
            self.f_sys = self.f_nom

        voltages_out = {}
        for node, v_val in voltages_complex.items():
            voltages_out[node] = {
                "V_pu": round(abs(v_val), 5),
                "V_volts": round(abs(v_val) * self.V_base, 2)
            }

        self.step_index += 1
        payload = {
            "step": self.step_index,
            "time_sec": round(self.step_index * self.dt, 2),
            "mode": self.mode,
            "mesh_type": self.mesh_type if self.mode == "SENSITIVITY" else "RADIAL",
            "operating_mode": getattr(self.solver, "operating_mode", self.operating_mode),
            "converged": conv,
            "iterations": iters,
            "voltages": voltages_out,
            "f_sys_hz": round(self.f_sys, 4),
            "omega_sys": round(self.f_sys * 2.0 * 3.141592653589793, 4),
            "P_net_w": round(p_net, 2),
            "comm_scenario": self.comm_emulator.scenario,
            "comm_delay_s": round(delay_applied, 4),
            "comm_nodes_received": len(filtered_injections),
            "comm_nodes_dropped": len(node_injections) - len(filtered_injections),
            "stale_nodes": stale_nodes,
            "tripped_nodes": list(self.tripped_nodes)
        }

        # Publicar los nuevos voltajes a todos los nodos
        self.pub_socket.send_json(payload)
        return payload

    def get_comm_stats(self):
        """Retorna las estadísticas acumuladas del emulador de comunicaciones."""
        return self.comm_emulator.get_stats()

    def close(self):
        """Cierra los sockets y destruye el contexto ZeroMQ."""
        self.rep_socket.close(linger=0)
        self.pub_socket.close(linger=0)
        self.context.term()

    def start_loop(self, max_steps=10):
        """Bucle principal de simulación determinista sin deriva temporal."""
        print(f"Reloj Maestro ZMQ iniciado en modo {self.mode} [Malla={self.mesh_type}] (Paso = {self.dt}s).")
        print(f"  Canal de comunicación: {self.comm_emulator}")
        print(f"  Escuchando en REP:{self.port_rep}, PUB:{self.port_pub}...")
        self.running = True

        poller = zmq.Poller()
        poller.register(self.rep_socket, zmq.POLLIN)
        last_injections = {}
        t_next = time.perf_counter()

        for step in range(max_steps):
            t_next += self.dt

            socks = dict(poller.poll(timeout=2000))
            if self.rep_socket in socks and socks[self.rep_socket] == zmq.POLLIN:
                try:
                    message = self.rep_socket.recv_json()
                    injections = message.get("injections", {})
                    last_injections = injections
                except zmq.ZMQError:
                    injections = last_injections
            else:
                injections = last_injections

            res = self.run_step(injections)

            try:
                self.rep_socket.send_json({"status": "OK", "step": res["step"]})
            except zmq.ZMQError:
                pass

            sleep_time = t_next - time.perf_counter()
            if sleep_time > 0:
                time.sleep(sleep_time)

        print("Simulación maestro completada.")
        print(f"  Estadísticas de comunicación: {self.comm_emulator.get_stats()}")

if __name__ == "__main__":
    top_file = os.path.join(os.path.dirname(__file__), "..", "config", "topologia_BT_4nodos.csv")
    master = MasterClockZMQ(top_file, mode="SENSITIVITY", mesh_type="RING_ZBUS")
    test_inj = {
        "2": {"P": 10000.0, "Q": 2000.0},
        "3": {"P": 5000.0, "Q": 1000.0},
        "4": {"P": -15000.0, "Q": -3000.0}
    }
    result = master.run_step(test_inj)
    print("Resultado prueba ZMQ Master (Sensibilidad RING_ZBUS):")
    print(json.dumps(result, indent=2))

