import sys
import os
import time
import argparse
import zmq

import csv
import math

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Demanda.SistemaDemanda import SistemaDemanda

class MultiLoadProcess:
    """
    Proceso de 3 Cargas (Nodos 4, 5 y 6) cohabitando en una sola Raspberry Pi (RPi 4 - 10.0.0.154).
    - Nodo 4: Carga Residencial (Forms/formatos/datos_demanda_A.csv)
    - Nodo 5: Carga Comercial   (Forms/formatos/datos_demanda_B.csv)
    - Nodo 6: Carga Industrial  (Forms/formatos/datos_demanda_C.csv)
    
    Se sincroniza con el Reloj Maestro del PC Central (SUB 5556) y reporta
    sus consumos agregados al Solucionador de Red (REQ 5555) en cada paso de 500 ms.
    """
    def __init__(self, master_host="10.0.0.156", port_rep=5555, port_pub=5556):
        self.master_host = master_host
        self.port_rep = port_rep
        self.port_pub = port_pub

        # Modelos de Carga y Series de Tiempo
        base_forms = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Forms"))
        self.ensayos_dir = os.path.join(base_forms, "ensayos_red_hil")
        legacy_dir = os.path.join(base_forms, "formatos")
        generados_dir = os.path.join(base_forms, "escenarios_generados")

        # Prioridad: escenario activo > ensayos_red_hil > formatos
        escenario_activo = self._resolver_escenario_activo(generados_dir)
        if escenario_activo:
            target_dir = escenario_activo
        else:
            target_dir = self.ensayos_dir if os.path.exists(self.ensayos_dir) else legacy_dir

        self.demanda_4_data = self._load_demanda_csv(os.path.join(target_dir, "datos_demanda_A.csv"))
        self.demanda_5_data = self._load_demanda_csv(os.path.join(target_dir, "datos_demanda_B.csv"))
        self.demanda_6_data = self._load_demanda_csv(os.path.join(target_dir, "datos_demanda_C.csv"))

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

    def _resolver_escenario_activo(self, generados_dir):
        """Devuelve la ruta del escenario activo si existe, o None."""
        marcador = os.path.join(generados_dir, "ACTIVO.txt")
        if not os.path.exists(marcador):
            return None
        try:
            with open(marcador, "r", encoding="utf-8") as f:
                nombre = f.read().strip()
        except OSError:
            return None
        if not nombre:
            return None
        ruta = os.path.join(generados_dir, nombre)
        return ruta if os.path.isdir(ruta) else None

    def _load_demanda_csv(self, file_path):
        data = []
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
                if not lines:
                    return data
                delim = ";" if ";" in lines[0] else ","
                reader = csv.reader(lines, delimiter=delim)
                header = [h.strip() for h in next(reader, [])]
                
                # Identificar índices de P y Q
                p_idx = header.index("P_kW") if "P_kW" in header else (header.index("P") if "P" in header else 1)
                q_idx = header.index("Q_kvar") if "Q_kvar" in header else (header.index("Q") if "Q" in header else 2)
                
                for row in reader:
                    if len(row) > max(p_idx, q_idx):
                        try:
                            # P y Q en kW y kvar en el CSV -> convertir a W y var
                            p_w = float(row[p_idx].replace(",", ".")) * 1000.0
                            q_var = float(row[q_idx].replace(",", ".")) * 1000.0
                            data.append((p_w, q_var))
                        except ValueError:
                            continue
        return data

    def run(self, max_steps=None):
        print("=" * 60)
        print(" PROCESO DE 3 CARGAS COHABITANTES (Nodos 4, 5 y 6)")
        print(f" - Perfiles Formatos: N4={len(self.demanda_4_data)}, N5={len(self.demanda_5_data)}, N6={len(self.demanda_6_data)} muestras")
        print(f" Conectando al PC Central en {self.master_host}...")
        print("=" * 60)

        self.running = True
        step_count = 0

        try:
            while self.running:
                try:
                    # Esperar tick del reloj maestro
                    clock_msg = self.sub_clock.recv_json()
                except zmq.Again:
                    print("[AVISO] Timeout esperando tick del PC Central. Reintentando...")
                    continue

                step_count += 1
                if max_steps and step_count > max_steps:
                    break

                step_idx = clock_msg.get("step", step_count)
                time_s = clock_msg.get("time_sec", step_idx * 0.5)

                # Evaluar demanda de cada nodo segun las series temporales de Formatos
                idx = step_idx - 1
                if self.demanda_4_data:
                    P4, Q4 = self.demanda_4_data[idx % len(self.demanda_4_data)]
                else:
                    var_4 = 1.0 + 0.05 * math.sin(0.2 * time_s)
                    P4, Q4 = 80000.0 * var_4, 20000.0 * var_4

                if self.demanda_5_data:
                    P5, Q5 = self.demanda_5_data[idx % len(self.demanda_5_data)]
                else:
                    var_5 = 1.0 + 0.08 * math.sin(0.3 * time_s + 1.0)
                    P5, Q5 = 60000.0 * var_5, 15000.0 * var_5

                if self.demanda_6_data:
                    P6, Q6 = self.demanda_6_data[idx % len(self.demanda_6_data)]
                else:
                    var_6 = 1.0 + 0.10 * math.sin(0.15 * time_s + 2.0)
                    P6, Q6 = 100000.0 * var_6, 30000.0 * var_6

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
                    try:
                        self.req_master.close(linger=0)
                    except Exception:
                        pass
                    self.req_master = self.context.socket(zmq.REQ)
                    self.req_master.setsockopt(zmq.RCVTIMEO, 500)
                    self.req_master.setsockopt(zmq.SNDTIMEO, 500)
                    self.req_master.connect(f"tcp://{self.master_host}:{self.port_rep}")

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
