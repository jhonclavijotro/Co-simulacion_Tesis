import sys
import os
import time
import argparse
import json
import zmq

import csv
import math

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mock_data.data_loader import MissingResourceDataError

class MultiLoadProcess:
    """
    Proceso de cargas cohabitantes en una Raspberry Pi (multi-load).

    Banco de 8 nodos (despliegue actual): N4..N8 en la RPi de cargas.
    Banco de 21 nodos: 5 cargas por RPi (N7..N11, N12..N16, N17..N21) mediante
    el argumento `nodos`.

    Fuente de datos:
      - **consolidado** (rev.5): `datos_demanda.csv` con `N{id}_P_kW`/`N{id}_Q_kvar`.
      - **legacy**: `datos_demanda_A..E.csv`, conservado para escenarios
        anteriores a 2026-11-01.

    Se sincroniza con el Reloj Maestro del PC Central (SUB 5556) y reporta
    sus consumos agregados al Solucionador de Red (REQ 5555) en cada paso de 500 ms.
    """
    # Respaldo histórico por nodo (solo si la serie falta en modo legacy).
    FALLBACK = {
        4: (80000.0, 20000.0, 0.20, 0.0),
        5: (60000.0, 15000.0, 0.30, 1.0),
        6: (100000.0, 30000.0, 0.15, 2.0),
        7: (2500.0, 1000.0, 0.25, 3.0),
        8: (2000.0, 800.0, 0.10, 0.5),
    }

    def __init__(self, master_host="10.0.0.156", port_rep=5555, port_pub=5556, nodos=None,
                 q_step_node=None, q_step_var=1000.0, q_step_start=None, q_step_duration=5.0,
                 q_step2_node=None, q_step2_var=1000.0, q_step2_start=None, q_step2_duration=5.0):
        self.master_host = master_host
        self.port_rep = port_rep
        self.port_pub = port_pub
        self.nodos_carga = [int(n) for n in (nodos if nodos else (4, 5, 6, 7, 8))]
        self.q_step_node = int(q_step_node) if q_step_node is not None else None
        self.q_step_var = float(q_step_var)
        self.q_step_start = float(q_step_start) if q_step_start is not None else None
        self.q_step_duration = float(q_step_duration)
        self.q_step2_node = int(q_step2_node) if q_step2_node is not None else None
        self.q_step2_var = float(q_step2_var)
        self.q_step2_start = float(q_step2_start) if q_step2_start is not None else None
        self.q_step2_duration = float(q_step2_duration)

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

        self.demandas = {}
        nombre_consolidado = "datos_demanda.csv"
        capa1_path = os.path.join(target_dir, "plantilla_configuracion_cosimulacion.json")
        if os.path.exists(capa1_path):
            try:
                with open(capa1_path, "r", encoding="utf-8") as f_c1:
                    capa1 = json.load(f_c1)
                arch_dem = (capa1.get("archivos_datos") or {}).get("demanda")
                if not arch_dem:
                    arch_dem = ((capa1.get("asignacion_nodos") or {}).get("nodos_demanda") or {}).get("archivo_serie")
                if arch_dem:
                    nombre_consolidado = os.path.basename(arch_dem)
            except Exception:
                pass

        ruta_consolidada = os.path.join(target_dir, nombre_consolidado)
        if not os.path.exists(ruta_consolidada):
            ruta_consolidada = os.path.join(target_dir, "datos_demanda.csv")

        if os.path.exists(ruta_consolidada):
            self.esquema = "consolidado"
            self.demandas = self._load_demanda_consolidada(ruta_consolidada)
        else:
            self.esquema = "legacy"
            for nodo in self.nodos_carga:
                letra = chr(ord("A") + nodo - 4)
                ruta = os.path.join(target_dir, f"datos_demanda_{letra}.csv")
                self.demandas[nodo] = self._load_demanda_csv(ruta)

        # S-O-34 / C3: Resolver excitación reactiva de carga desde meta.json si no vino por CLI
        if self.q_step_node is None:
            meta_path = os.path.join(target_dir, "meta.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f_meta:
                        meta_cfg = json.load(f_meta)
                    ex_q = meta_cfg.get("excitacion_reactiva") or {}
                    if "nodo" in ex_q:
                        self.q_step_node = int(ex_q["nodo"])
                        self.q_step_var = float(ex_q.get("q_step_var", 1000.0))
                        self.q_step_start = float(ex_q.get("inicio_s", 50.0))
                        self.q_step_duration = float(ex_q.get("duracion_s", 5.0))
                    ex_q2 = meta_cfg.get("excitacion_reactiva_2") or {}
                    if "nodo" in ex_q2:
                        self.q_step2_node = int(ex_q2["nodo"])
                        self.q_step2_var = float(ex_q2.get("q_step_var", 1000.0))
                        self.q_step2_start = float(ex_q2.get("inicio_s", 100.0))
                        self.q_step2_duration = float(ex_q2.get("duracion_s", 5.0))
                except Exception:
                    pass

        # Atributos heredados (compatibilidad con scripts externos del banco de 8)
        self.demanda_4_data = self.demandas.get(4, [])
        self.demanda_5_data = self.demandas.get(5, [])
        self.demanda_6_data = self.demandas.get(6, [])
        self.demanda_7_data = self.demandas.get(7, [])
        self.demanda_8_data = self.demandas.get(8, [])

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
                # Tolerar BOM: un marcador con BOM no debe forzar el modo legacy.
                nombre = f.read().lstrip("\ufeff").strip()
        except OSError:
            return None
        if not nombre:
            return None
        ruta = os.path.join(generados_dir, nombre)
        return ruta if os.path.isdir(ruta) else None

    @staticmethod
    def _leer_csv(file_path):
        with open(file_path, "r", encoding="utf-8", newline="") as f:
            lines = [l for l in f if l.strip() and not l.strip().startswith("#")]
        if not lines:
            return [], []
        delim = ";" if ";" in lines[0] else ","
        reader = csv.reader(lines, delimiter=delim)
        header = [h.strip() for h in next(reader, [])]
        filas = [[c.strip().replace(",", ".") for c in row] for row in reader if row]
        return header, filas

    def _load_demanda_csv(self, file_path, nodo=None):
        """Carga P/Q por nombre de columna; nunca por posición fija."""
        data = []
        if not os.path.exists(file_path):
            return data
        header, filas = self._leer_csv(file_path)

        candidatos_p = ([f"N{nodo}_P_kW", f"N{nodo}_P", f"P_D{nodo}_kW"] if nodo else []) + ["P_kW", "P"]
        candidatos_q = ([f"N{nodo}_Q_kvar", f"N{nodo}_Q", f"Q_D{nodo}_kvar"] if nodo else []) + ["Q_kvar", "Q"]
        p_idx = next((header.index(c) for c in candidatos_p if c in header), None)
        q_idx = next((header.index(c) for c in candidatos_q if c in header), None)
        if p_idx is None or q_idx is None:
            raise ValueError(
                f"No se encontraron columnas P/Q reconocibles en {file_path}. "
                f"Cabecera: {header}")

        for row in filas:
            if len(row) > max(p_idx, q_idx):
                try:
                    # P y Q en kW y kvar en el CSV -> convertir a W y var
                    p_w = float(row[p_idx]) * 1000.0
                    q_var = float(row[q_idx]) * 1000.0
                    data.append((p_w, q_var))
                except ValueError:
                    continue
        return data

    def _load_demanda_consolidada(self, file_path):
        """Lee `datos_demanda.csv` por nodo. Falla si falta una columna declarada."""
        header, _ = self._leer_csv(file_path)
        if "tiempo_s" not in header:
            raise MissingResourceDataError(
                f"{os.path.basename(file_path)} sin columna 'tiempo_s' (cabecera: {header}).")
        resultado = {}
        for nodo in self.nodos_carga:
            if f"N{nodo}_P_kW" not in header or f"N{nodo}_Q_kvar" not in header:
                raise MissingResourceDataError(
                    f"{os.path.basename(file_path)} no tiene N{nodo}_P_kW / N{nodo}_Q_kvar. "
                    f"El proceso de cargas declara los nodos {self.nodos_carga}."
                )
            resultado[nodo] = self._load_demanda_csv(file_path, nodo=nodo)
        return resultado

    def _fallback(self, nodo, time_s):
        """Demanda de respaldo histórica (solo banco de 8, solo modo legacy)."""
        if nodo in self.FALLBACK:
            p_base, q_base, w, fase = self.FALLBACK[nodo]
            variacion = 1.0 + 0.05 * math.sin(w * time_s + fase)
            return p_base * variacion, q_base * variacion
        return 0.0, 0.0

    def run(self, max_steps=None):
        print("=" * 60)
        print(f" PROCESO MULTI-CARGA ({', '.join(f'N{n}' for n in self.nodos_carga)})")
        print(f" - Esquema: {self.esquema}")
        print(" - Muestras: " + ", ".join(
            f"N{n}={len(self.demandas.get(n, []))}" for n in self.nodos_carga))
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
                time_s = clock_msg.get("time_s", clock_msg.get("time_sec", (step_idx - 1) * 0.5))

                # Evaluar demanda de cada nodo segun las series temporales (en tiempo físico @ 0.5 s)
                idx = max(0, int(float(time_s) / 0.5 + 1e-6))
                demandas_paso = {}
                for nodo in self.nodos_carga:
                    serie = self.demandas.get(nodo) or []
                    if serie:
                        p_val, q_val = serie[min(idx, len(serie) - 1)]
                    else:
                        p_val, q_val = self._fallback(nodo, time_s)

                    # S-O-34 / C3: Perturbación física de reactiva (escalón en nodo de carga por duracion determinada)
                    if (self.q_step_node is not None and nodo == self.q_step_node
                            and self.q_step_start is not None
                            and self.q_step_start <= time_s < (self.q_step_start + self.q_step_duration)):
                        q_val += self.q_step_var

                    # S-O-43 / T2-P5: Segundo escalón de reactiva
                    if (self.q_step2_node is not None and nodo == self.q_step2_node
                            and self.q_step2_start is not None
                            and self.q_step2_start <= time_s < (self.q_step2_start + self.q_step2_duration)):
                        q_val += self.q_step2_var

                    demandas_paso[nodo] = (p_val, q_val)

                p_load_total_w = sum(p for p, _ in demandas_paso.values())
                q_load_total_var = sum(q for _, q in demandas_paso.values())

                # Inyecciones para el flujo de potencia: las cargas consumen (potencia negativa)
                payload = {
                    "source": "LOADS_RPi",
                    "step": step_idx,
                    "P_load_total_w": round(p_load_total_w, 2),
                    "Q_load_total_var": round(q_load_total_var, 2),
                    "injections": {
                        str(n): {"P": round(-p, 2), "Q": round(-q, 2)}
                        for n, (p, q) in demandas_paso.items()
                    }
                }

                try:
                    self.req_master.send_json(payload)
                    ack = self.req_master.recv_json()
                except Exception:
                    try:
                        self.req_master.close(linger=0)
                    except Exception:
                        pass
                    self.req_master = self.context.socket(zmq.REQ)
                    self.req_master.setsockopt(zmq.RCVTIMEO, 500)
                    self.req_master.setsockopt(zmq.SNDTIMEO, 500)
                    self.req_master.connect(f"tcp://{self.master_host}:{self.port_rep}")

                if step_idx % 2 == 0:
                    p_tot = sum(p for p, _ in demandas_paso.values()) / 1000.0
                    q_tot = sum(q for _, q in demandas_paso.values()) / 1000.0
                    detalle = ", ".join(
                        f"N{n}={p/1000:.1f}k" for n, (p, _) in demandas_paso.items())
                    print(f"[Cargas RPi] Paso {step_idx:04d}: Demanda Total = {p_tot:.1f} kW, "
                          f"{q_tot:.1f} kvar ({detalle})")

        except KeyboardInterrupt:
            print("\nDeteniendo proceso de cargas...")
        finally:
            self.sub_clock.close()
            self.req_master.close()
            self.context.term()
            print("Proceso de cargas finalizado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Proceso Multi-Carga (multi-load por RPi)")
    parser.add_argument("--master-host", default="10.0.0.156", help="IP del PC Central")
    parser.add_argument("--port-rep", type=int, default=5555, help="Puerto REP de inyecciones")
    parser.add_argument("--port-pub", type=int, default=5556, help="Puerto PUB del reloj")
    parser.add_argument("--steps", type=int, default=None, help="Pasos de simulacion")
    parser.add_argument("--nodos", default=None,
                        help="Nodos de carga separados por coma (p. ej. 7,8,9,10,11)")
    parser.add_argument("--q-step-node", type=int, default=None, help="Nodo para escalón de reactiva (S-O-34 C3)")
    parser.add_argument("--q-step-var", type=float, default=1000.0, help="Magnitud del escalón de reactiva [var]")
    parser.add_argument("--q-step-start", type=float, default=None, help="Inicio del escalón de reactiva [s]")
    parser.add_argument("--q-step-duration", type=float, default=5.0, help="Duración del escalón de reactiva [s]")
    parser.add_argument("--q-step2-node", type=int, default=None, help="Nodo para segundo escalón de reactiva (S-O-43 T2-P5)")
    parser.add_argument("--q-step2-var", type=float, default=1000.0, help="Magnitud del segundo escalón [var]")
    parser.add_argument("--q-step2-start", type=float, default=None, help="Inicio del segundo escalón [s]")
    parser.add_argument("--q-step2-duration", type=float, default=5.0, help="Duración del segundo escalón [s]")
    args = parser.parse_args()

    nodos = [int(n) for n in args.nodos.split(",")] if args.nodos else None
    proc = MultiLoadProcess(
        master_host=args.master_host,
        port_rep=args.port_rep,
        port_pub=args.port_pub,
        nodos=nodos,
        q_step_node=args.q_step_node,
        q_step_var=args.q_step_var,
        q_step_start=args.q_step_start,
        q_step_duration=args.q_step_duration,
        q_step2_node=args.q_step2_node,
        q_step2_var=args.q_step2_var,
        q_step2_start=args.q_step2_start,
        q_step2_duration=args.q_step2_duration
    )
    proc.run(max_steps=args.steps)
