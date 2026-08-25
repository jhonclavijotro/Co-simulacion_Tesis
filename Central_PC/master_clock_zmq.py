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
                 V_base=400.0, S_base=100000.0, port_rep=5555, port_pub=5556,
                 comm_scenario="IDEAL", comm_seed=None):
        self.topology_csv = topology_csv
        self.mode = mode.upper()
        self.mesh_type = mesh_type.upper()
        self.V_base = V_base
        self.S_base = S_base
        self.port_rep = port_rep
        self.port_pub = port_pub

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

        # Emulador de Canal de Comunicación
        self.comm_emulator = CommunicationEmulator(scenario=comm_scenario, seed=comm_seed)

        # ZeroMQ Setup
        self.context = zmq.Context()
        self.rep_socket = self.context.socket(zmq.REP)
        self.rep_socket.setsockopt(zmq.LINGER, 0)
        self.rep_socket.bind(f"tcp://*:{self.port_rep}")

        self.pub_socket = self.context.socket(zmq.PUB)
        self.pub_socket.setsockopt(zmq.LINGER, 0)
        self.pub_socket.bind(f"tcp://*:{self.port_pub}")

        self.running = False

    def run_step(self, node_injections):
        """
        Ejecuta un paso maestro de flujo de potencia con las inyecciones recolectadas.

        Si el emulador de comunicaciones está activo (escenario != IDEAL), introduce:
          1. Retardo variable (latencia/jitter) antes de procesar las inyecciones.
          2. Pérdida de paquetes: descarte aleatorio de inyecciones de nodo.

        Parámetros:
            node_injections: {node_id: {"P": watts, "Q": vars}}

        Retorna:
            Dict con el payload de resultados del paso de simulación.
        """
        # Emular retardo de comunicación
        delay_applied = self.comm_emulator.apply_delay()

        # Emular pérdida de paquetes: filtrar inyecciones
        filtered_injections = self.comm_emulator.filter_injections(node_injections)

        P_dict = {int(k): v["P"] for k, v in filtered_injections.items()}
        Q_dict = {int(k): v["Q"] for k, v in filtered_injections.items()}

        voltages_complex, conv, iters = self.solver.solve(P_dict, Q_dict)

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
            "converged": conv,
            "iterations": iters,
            "voltages": voltages_out,
            "comm_scenario": self.comm_emulator.scenario,
            "comm_delay_s": round(delay_applied, 4),
            "comm_nodes_received": len(filtered_injections),
            "comm_nodes_dropped": len(node_injections) - len(filtered_injections),
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
        """Bucle principal de simulación."""
        print(f"Reloj Maestro ZMQ iniciado en modo {self.mode} [Malla={self.mesh_type}] (Paso = {self.dt}s).")
        print(f"  Canal de comunicación: {self.comm_emulator}")
        print(f"  Escuchando en REP:{self.port_rep}, PUB:{self.port_pub}...")
        self.running = True

        for step in range(max_steps):
            message = self.rep_socket.recv_json()
            injections = message.get("injections", {})

            res = self.run_step(injections)
            self.rep_socket.send_json({"status": "OK", "step": res["step"]})

            time.sleep(self.dt)

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

