import sys
import os
import time
import argparse
import zmq

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Demanda.SistemaDemanda import SistemaDemanda

class MultiLoadProcess:
    """
    Proceso de 3 Cargas (Nodos 4, 5 y 6) cohabitando en una sola Raspberry Pi (RPi 4 - 10.0.0.154).
    - Nodo 4: Carga Residencial (Nominal: 80 kW, 20 kvar)
    - Nodo 5: Carga Comercial   (Nominal: 60 kW, 15 kvar)
    - Nodo 6: Carga Industrial  (Nominal: 100 kW, 30 kvar)
    
    Se sincroniza con el Reloj Maestro del PC Central (SUB 5556) y reporta
    sus consumos agregados al Solucionador de Red (REQ 5555) en cada paso de 500 ms.
    """
    def __init__(self, master_host="10.0.0.156", port_rep=5555, port_pub=5556):
        self.master_host = master_host
        self.port_rep = port_rep
        self.port_pub = port_pub

        # Modelos de Carga
        self.load_4 = SistemaDemanda(P_nominal=80000.0, Q_nominal=20000.0)
        self.load_5 = SistemaDemanda(P_nominal=60000.0, Q_nominal=15000.0)
        self.load_6 = SistemaDemanda(P_nominal=100000.0, Q_nominal=30000.0)

        # Configuración Sockets ZeroMQ
        self.context = zmq.Context()
        self.sub_clock = self.context.socket(zmq.SUB)
        self.sub_clock.setsockopt(zmq.SUBSCRIBE, b"")
        self.sub_clock.setsockopt(zmq.RCVTIMEO, 2500)
        self.sub_clock.connect(f"tcp://{self.master_host}:{self.port_pub}")

        self.req_master = self.context.socket(zmq.REQ)
        self.req_master.setsockopt(zmq.RCVTIMEO, 2000)
        self.req_master.setsockopt(zmq.SNDTIMEO, 1000)
        self.req_master.connect(f"tcp://{self.master_host}:{self.port_rep}")

        self.running = False

    def run(self, max_steps=None):
        print("=" * 60)
        print(" PROCESO DE 3 CARGAS COHABITANTES (Nodos 4, 5 y 6)")
        print(f" Conectando al PC Central en {self.master_host}...")
        print("=" * 60)

        self.running = True
        step_count = 0

        try:
            while self.running:
                step_count += 1
                if max_steps and step_count > max_steps:
                    break

                try:
                    # Esperar tick del reloj maestro
                    clock_msg = self.sub_clock.recv_json()
                except zmq.Again:
                    print("[AVISO] Timeout esperando tick del PC Central. Reintentando...")
                    continue

                step_idx = clock_msg.get("step", step_count)
                time_s = clock_msg.get("time_sec", step_idx * 0.5)

                # Calcular demanda de cada nodo (con pequeñas variaciones temporales)
                # Factor de variabilidad suave basado en el tiempo
                import math
                var_4 = 1.0 + 0.05 * math.sin(0.2 * time_s)
                var_5 = 1.0 + 0.08 * math.sin(0.3 * time_s + 1.0)
                var_6 = 1.0 + 0.10 * math.sin(0.15 * time_s + 2.0)

                P4 = 80000.0 * var_4
                Q4 = 20000.0 * var_4

                P5 = 60000.0 * var_5
                Q5 = 15000.0 * var_5

                P6 = 100000.0 * var_6
                Q6 = 30000.0 * var_6

                # Inyecciones para el flujo de potencia: las cargas consumen (potencia negativa)
                payload = {
                    "source": "LOADS_RPi4",
                    "step": step_idx,
                    "injections": {
                        "4": {"P": round(-P4, 2), "Q": round(-Q4, 2)},
                        "5": {"P": round(-P5, 2), "Q": round(-Q5, 2)},
                        "6": {"P": round(-P6, 2), "Q": round(-Q6, 2)}
                    }
                }

                try:
                    self.req_master.send_json(payload)
                    ack = self.req_master.recv_json()
                except Exception as e:
                    print(f"[ERROR] Error enviando inyecciones al PC Central: {e}")

                if step_idx % 2 == 0:
                    p_tot = (P4 + P5 + P6) / 1000.0
                    q_tot = (Q4 + Q5 + Q6) / 1000.0
                    print(f"[Cargas RPi4] Paso {step_idx:04d}: Demanda Total = {p_tot:.1f} kW, {q_tot:.1f} kvar (N4={P4/1000:.1f}k, N5={P5/1000:.1f}k, N6={P6/1000:.1f}k)")

        except KeyboardInterrupt:
            print("\nDeteniendo proceso de cargas...")
        finally:
            self.sub_clock.close()
            self.req_master.close()
            self.context.term()
            print("Proceso de cargas finalizado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Proceso Multi-Carga (Nodos 4, 5, 6)")
    parser.add_argument("--master-host", default="10.0.0.156", help="IP del PC Central")
    parser.add_argument("--port-rep", type=int, default=5555, help="Puerto REP de inyecciones")
    parser.add_argument("--port-pub", type=int, default=5556, help="Puerto PUB del reloj")
    parser.add_argument("--steps", type=int, default=None, help="Pasos de simulacion")
    args = parser.parse_args()

    proc = MultiLoadProcess(master_host=args.master_host, port_rep=args.port_rep, port_pub=args.port_pub)
    proc.run(max_steps=args.steps)
