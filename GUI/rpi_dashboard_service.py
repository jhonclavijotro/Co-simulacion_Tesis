# -*- coding: utf-8 -*-
import sys
import os
import time
import argparse
import csv
import json
import threading
import http.server
import socketserver
import subprocess
import math
import re
from urllib.parse import urlparse
try:
    import zmq
except ImportError:
    zmq = None

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

GUI_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(GUI_DIR, ".."))

def get_python_executable():
    """Detecta el intérprete Python del entorno virtual (.venv) o el global."""
    venv_win = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
    if os.path.exists(venv_win):
        return venv_win
    venv_linux = os.path.join(BASE_DIR, ".venv", "bin", "python")
    if os.path.exists(venv_linux):
        return venv_linux
    return sys.executable

def load_cables_catalog():
    """Carga el catálogo canónico de cables desde Forms/cables.csv."""
    cables_file = os.path.abspath(os.path.join(BASE_DIR, "Forms", "cables.csv"))
    cables = []
    if os.path.exists(cables_file):
        try:
            with open(cables_file, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get("Nombre / Calibre", "").strip()
                    if name:
                        cables.append({
                            "name": name,
                            "type": row.get("Tipo de cable", "").strip(),
                            "material": row.get("Material del conductor", "").strip(),
                            "r_dc": row.get("Resistencia DC max a 20°C", "").strip(),
                            "ampacity": row.get("Ampacidad (A)", "").strip(),
                            "section": row.get("Sección Conductor (mm²)", "").strip()
                        })
        except Exception as e:
            print(f"[WARN] Error cargando cables.csv: {e}")
    if not cables:
        cables = [
            {"name": "4/0 AWG (Penguin)", "type": "ACSR", "r_dc": "0,265 Ohm/km", "ampacity": "366,0 A"},
            {"name": "1/0 AWG (Raven)", "type": "ACSR", "r_dc": "0,532 Ohm/km", "ampacity": "243,0 A"},
            {"name": "2 AWG (Sparrow)", "type": "ACSR", "r_dc": "0,846 Ohm/km", "ampacity": "184,0 A"},
            {"name": "4 AWG (Swan)", "type": "ACSR", "r_dc": "1,346 Ohm/km", "ampacity": "139,0 A"},
            {"name": "266.8 KCMIL (Partridge)", "type": "ACSR", "r_dc": "0,213 Ohm/km", "ampacity": "457,0 A"},
            {"name": "336.4 KCMIL (Linnet)", "type": "ACSR", "r_dc": "0,168 Ohm/km", "ampacity": "529,0 A"},
            {"name": "Aluminio Aislado 50 mm²", "type": "Aislado", "r_dc": "0,350 Ohm/km", "ampacity": "100,0 A"}
        ]
    return cables

# Coordenadas geográficas por defecto (Feeder distribución real, entorno Bogotá / Sabana)
DEFAULT_GEO_COORDS = {
    1: {"lat": 4.71100, "lon": -74.07210, "type": "DIESEL", "name": "Planta Diésel 15 kVA (Slack)", "role": "Slack Líder"},
    2: {"lat": 4.71180, "lon": -74.07140, "type": "SOLAR", "name": "Instalación Solar FV 5 kW", "role": "DER Seguidor"},
    3: {"lat": 4.71030, "lon": -74.07280, "type": "BESS", "name": "Almacenamiento BESS 3 kWh", "role": "DER Seguidor"},
    4: {"lat": 4.71260, "lon": -74.07090, "type": "LOAD", "name": "Carga Residencial (Nodo 4)", "role": "Demanda Dinámica"},
    5: {"lat": 4.71220, "lon": -74.07030, "type": "LOAD", "name": "Carga Comercial (Nodo 5)", "role": "Demanda Dinámica"},
    6: {"lat": 4.70950, "lon": -74.07340, "type": "LOAD", "name": "Carga Industrial (Nodo 6)", "role": "Demanda Dinámica"},
    7: {"lat": 4.70990, "lon": -74.07420, "type": "LOAD", "name": "Carga Residencial D (Nodo 7)", "role": "Demanda Dinámica"},
    8: {"lat": 4.70910, "lon": -74.07490, "type": "LOAD", "name": "Carga Residencial E (Nodo 8)", "role": "Demanda Dinámica"}
}

# Estado global compartido en memoria para la API REST del Dashboard
latest_telemetry_state = {
    "current_step": 0,
    "time_sec": 0.0,
    "f_sys_hz": 60.0,
    "P_net_kW": 0.0,
    "hold_mode": "ZOH",
    "zfoh_lambda": 0.70,
    "network_profile": "LAN_ETHERNET",
    "active_scenario": "ESC-HIL-003_consolidado_rev5",
    "cosim_variables": {
        "duration_s": 300.0,
        "max_steps": 600,
        "dt_macro_s": 0.5,
        "solver_mode": "FBS",
        "mesh_type": "RADIAL",
        "slack_mode": "RIGIDO",
        "hold_mode": "ZOH",
        "zfoh_lambda": 0.70,
        "network_profile": "LAN_ETHERNET"
    },
    "simulation_status": {
        "running": False,
        "model": "run_simulation_bt_formatos",
        "pid": None,
        "step": 0,
        "max_steps": 600,
        "progress_pct": 0.0,
        "elapsed_s": 0.0,
        "message": "En reposo"
    },
    "topology_config": {
        "v_base": 400.0,
        "s_base": 10000.0,
        "preset": "ESC-HIL-003_consolidado_rev5",
        "branches": [
            {"from": 1, "to": 2, "conductor": "4 AWG (Swan)", "length_km": 0.10, "R_ohm": 0.040, "X_ohm": 0.012, "max_current_A": 250},
            {"from": 1, "to": 3, "conductor": "4 AWG (Swan)", "length_km": 0.12, "R_ohm": 0.045, "X_ohm": 0.014, "max_current_A": 250},
            {"from": 2, "to": 4, "conductor": "4 AWG (Swan)", "length_km": 0.15, "R_ohm": 0.060, "X_ohm": 0.018, "max_current_A": 200},
            {"from": 2, "to": 5, "conductor": "4 AWG (Swan)", "length_km": 0.18, "R_ohm": 0.070, "X_ohm": 0.020, "max_current_A": 200},
            {"from": 3, "to": 6, "conductor": "4 AWG (Swan)", "length_km": 0.12, "R_ohm": 0.050, "X_ohm": 0.015, "max_current_A": 200},
            {"from": 3, "to": 7, "conductor": "4 AWG (Swan)", "length_km": 0.20, "R_ohm": 0.080, "X_ohm": 0.022, "max_current_A": 200},
            {"from": 7, "to": 8, "conductor": "4 AWG (Swan)", "length_km": 0.14, "R_ohm": 0.055, "X_ohm": 0.016, "max_current_A": 160}
        ],
        "nodes": {
            str(k): dict(v) for k, v in DEFAULT_GEO_COORDS.items()
        }
    },
    "exogenous_profiles": {
        "solar": {"target_node": 2, "source_file": "datos_meteorologicos.csv", "irradiance_w_m2": 1000.0, "temp_c": 25.0, "status": "Activo"},
        "wind": {"target_node": 3, "source_file": "datos_meteorologicos.csv", "wind_speed_ms": 8.5, "status": "En Reserva"},
        "hydro": {"target_node": 4, "source_file": "datos_meteorologicos.csv", "flow_rate_m3s": 1.5, "status": "En Reserva"}
    },
    "latest_result": {
        "step": 0,
        "voltages": {
            "1": {"V_volts": 400.0, "V_pu": 1.0000, "P": 0.0, "Q": 0.0},
            "2": {"V_volts": 400.1, "V_pu": 1.0003, "P": 2000.0, "Q": 0.0},
            "3": {"V_volts": 400.39, "V_pu": 1.0010, "P": 750.0, "Q": 0.0},
            "4": {"V_volts": 400.23, "V_pu": 1.0006, "P": -2850.0, "Q": -940.0},
            "5": {"V_volts": 400.57, "V_pu": 1.0014, "P": -1960.0, "Q": -400.0},
            "6": {"V_volts": 400.62, "V_pu": 1.0016, "P": -1470.0, "Q": -300.0},
            "7": {"V_volts": 400.00, "V_pu": 1.0000, "P": -1000.0, "Q": -200.0},
            "8": {"V_volts": 400.00, "V_pu": 1.0000, "P": -600.0, "Q": -120.0}
        },
        "network_stats": {
            "profile": "LAN_ETHERNET",
            "avg_delay_ms": 1.2,
            "packet_loss_ratio": 0.0
        }
    },
    "q_ratios": {"1": 0.3074, "2": 0.3074, "3": 0.3074},
    "errors": {"err_q_12": 0.0, "err_q_23": 0.0, "err_v_12": 0.0, "err_v_23": 0.0},
    "logs": [
        {"timestamp": time.strftime("%H:%M:%S"), "message": "Servicio de Dashboard & Storage RPi DATA inicializado.", "level": "info"}
    ]
}

state_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Gestión de Escenarios y Evaluaciones
# ---------------------------------------------------------------------------

def list_available_scenarios():
    """Descubre los escenarios disponibles en Forms/escenarios_generados/."""
    generados_dir = os.path.join(BASE_DIR, "Forms", "escenarios_generados")
    activo_file = os.path.join(generados_dir, "ACTIVO.txt")
    active_name = ""
    if os.path.exists(activo_file):
        try:
            with open(activo_file, "r", encoding="utf-8-sig") as f:
                active_name = f.read().strip()
        except Exception:
            pass

    scenarios = []
    if os.path.exists(generados_dir):
        for entry in sorted(os.listdir(generados_dir)):
            p = os.path.join(generados_dir, entry)
            if os.path.isdir(p):
                has_capa1 = os.path.exists(os.path.join(p, "plantilla_configuracion_cosimulacion.json"))
                topos = [f for f in os.listdir(p) if f.startswith("topologia_red_") and f.endswith(".csv")]
                has_meteo = os.path.exists(os.path.join(p, "datos_meteorologicos.csv"))
                has_demanda = os.path.exists(os.path.join(p, "datos_demanda.csv"))
                node_count = 8
                if topos:
                    if "21" in topos[0]:
                        node_count = 21
                    elif "8" in topos[0]:
                        node_count = 8
                    elif "6" in topos[0]:
                        node_count = 6

                scenarios.append({
                    "name": entry,
                    "is_active": (entry == active_name),
                    "node_count": node_count,
                    "has_capa1": has_capa1,
                    "has_topology": len(topos) > 0,
                    "topology_file": topos[0] if topos else None,
                    "has_meteo": has_meteo,
                    "has_demanda": has_demanda,
                    "is_complete": has_capa1 and len(topos) > 0 and has_meteo and has_demanda
                })
    return {"active": active_name, "scenarios": scenarios}

def select_active_scenario(scenario_name: str):
    """Establece un escenario como activo y recarga su topología y Capa 1."""
    generados_dir = os.path.join(BASE_DIR, "Forms", "escenarios_generados")
    scen_path = os.path.join(generados_dir, scenario_name)
    if not os.path.isdir(scen_path):
        return False, f"El escenario '{scenario_name}' no existe."

    activo_file = os.path.join(generados_dir, "ACTIVO.txt")
    with open(activo_file, "w", encoding="utf-8") as f:
        f.write(scenario_name)

    # Cargar topología del escenario
    topos = [f for f in os.listdir(scen_path) if f.startswith("topologia_red_") and f.endswith(".csv")]
    branches = []
    nodes_found = set()
    if topos:
        topo_csv = os.path.join(scen_path, topos[0])
        with open(topo_csv, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader([l for l in f if not l.strip().startswith("#")])
            for row in reader:
                u = int(row["from_node"])
                v = int(row["to_node"])
                nodes_found.add(u)
                nodes_found.add(v)
                branches.append({
                    "from": u,
                    "to": v,
                    "conductor": row.get("cable_type", "4 AWG (Swan)"),
                    "length_km": float(row.get("length_km", 0.1)),
                    "R_ohm": float(row.get("R_ohm", 0.04)),
                    "X_ohm": float(row.get("X_ohm", 0.012)),
                    "max_current_A": float(row.get("max_current_A", 200))
                })

    # Cargar Capa 1 si existe
    capa1_path = os.path.join(scen_path, "plantilla_configuracion_cosimulacion.json")
    v_base = 400.0
    s_base = 10000.0
    if os.path.exists(capa1_path):
        try:
            with open(capa1_path, "r", encoding="utf-8") as f:
                c1 = json.load(f)
                pg = c1.get("parametros_generales", {})
                v_base = float(pg.get("tension_base_V", 400.0))
                s_base = float(pg.get("potencia_base_kVA", 10.0)) * 1000.0
        except Exception:
            pass

    # Generar nodos con coordenadas geográficas
    nodes = {}
    for n in sorted(list(nodes_found or range(1, 9))):
        if n in DEFAULT_GEO_COORDS:
            nodes[str(n)] = dict(DEFAULT_GEO_COORDS[n])
        else:
            # Algoritmo de dispersión geográfica sintética realista
            angle = (n * 0.45) % (2 * math.pi)
            dist_km = 0.08 + (n * 0.02)
            dlat = (dist_km / 111.32) * math.cos(angle)
            dlon = (dist_km / (111.32 * math.cos(math.radians(4.711)))) * math.sin(angle)
            nodes[str(n)] = {
                "lat": round(4.71100 + dlat, 5),
                "lon": round(-74.07210 + dlon, 5),
                "type": "LOAD",
                "name": f"Nodo de Carga {n}",
                "role": "Demanda Dinámica"
            }

    with state_lock:
        latest_telemetry_state["active_scenario"] = scenario_name
        latest_telemetry_state["topology_config"] = {
            "v_base": v_base,
            "s_base": s_base,
            "preset": scenario_name,
            "branches": branches,
            "nodes": nodes
        }
        latest_telemetry_state["logs"].append({
            "timestamp": time.strftime("%H:%M:%S"),
            "message": f"Escenario activo cambiado a: {scenario_name} ({len(nodes)} nodos, {len(branches)} ramas).",
            "level": "info"
        })

    return True, f"Escenario '{scenario_name}' activado exitosamente."

def save_uploaded_evaluation(scenario_name: str, capa1_content: str, topo_content: str,
                             meteo_content: str, demanda_content: str, activate: bool = True):
    """Guarda los 4 archivos de un paquete de evaluación consolidado."""
    if not scenario_name or not re.match(r'^[a-zA-Z0-9_\-]+$', scenario_name):
        return False, "Nombre de escenario inválido. Use solo letras, números, guiones y guiones bajos."

    target_dir = os.path.join(BASE_DIR, "Forms", "escenarios_generados", scenario_name)
    os.makedirs(target_dir, exist_ok=True)

    try:
        if capa1_content:
            with open(os.path.join(target_dir, "plantilla_configuracion_cosimulacion.json"), "w", encoding="utf-8") as f:
                f.write(capa1_content)

        if topo_content:
            # Detectar número de nodos para nombre de topología
            n_nodes = 8
            if "21" in topo_content or len(topo_content.strip().split("\n")) > 15:
                n_nodes = 21
            with open(os.path.join(target_dir, f"topologia_red_{n_nodes}nodos.csv"), "w", encoding="utf-8") as f:
                f.write(topo_content)

        if meteo_content:
            with open(os.path.join(target_dir, "datos_meteorologicos.csv"), "w", encoding="utf-8") as f:
                f.write(meteo_content)

        if demanda_content:
            with open(os.path.join(target_dir, "datos_demanda.csv"), "w", encoding="utf-8") as f:
                f.write(demanda_content)

        # Copiar catálogo canónico si no existe
        cables_dest = os.path.join(target_dir, "cables.csv")
        if not os.path.exists(cables_dest):
            cables_src = os.path.join(BASE_DIR, "Forms", "cables.csv")
            if os.path.exists(cables_src):
                import shutil
                shutil.copy(cables_src, cables_dest)

        if activate:
            select_active_scenario(scenario_name)

        return True, f"Evaluación '{scenario_name}' guardada correctamente."
    except Exception as e:
        return False, f"Error escribiendo archivos de evaluación: {e}"

# ---------------------------------------------------------------------------
# Gestor de Procesos de Ejecución de Modelos de Simulación
# ---------------------------------------------------------------------------

class SimulationProcessManager:
    """Administra la ejecución asíncrona de los scripts de simulación y monitorea telemetría."""
    def __init__(self):
        self.proc = None
        self.thread = None
        self.running = False
        self.model = "run_simulation_bt_formatos"
        self.max_steps = 600
        self.current_step = 0
        self.start_time = None
        self.output_csv = None
        self.lock = threading.Lock()

    def start(self, model="run_simulation_bt_formatos", steps=600):
        with self.lock:
            if self.running and self.proc and self.proc.poll() is None:
                return False, "Ya existe un modelo de simulación en ejecución."

            self.model = model
            self.max_steps = int(steps)
            self.current_step = 0
            self.start_time = time.time()
            self.running = True

            scripts_dir = os.path.join(BASE_DIR, "Scripts")
            python_exe = get_python_executable()

            if model == "run_pilot_test":
                script_path = os.path.join(scripts_dir, "run_pilot_test.py")
                cmd = [python_exe, script_path]
                self.output_csv = os.path.join(BASE_DIR, "output_data", "telemetry_monitor_pilot_30steps.csv")
                self.max_steps = 30
            elif model == "run_formal_experiment":
                script_path = os.path.join(scripts_dir, "run_formal_experiment_600steps.py")
                cmd = [python_exe, script_path, "--steps", str(self.max_steps)]
                self.output_csv = os.path.join(BASE_DIR, "output_data", "telemetry_monitor_cluster_8nodes_hil.csv")
            else:  # run_simulation_bt_formatos
                script_path = os.path.join(scripts_dir, "run_simulation_bt_formatos.py")
                out_csv = os.path.join(BASE_DIR, "output_data", "telemetry_monitor_formatos_bt.csv")
                cmd = [python_exe, script_path, "--steps", str(self.max_steps), "--output-csv", out_csv]
                self.output_csv = out_csv

            try:
                self.proc = subprocess.Popen(
                    cmd,
                    cwd=BASE_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
            except Exception as e:
                self.running = False
                return False, f"Error iniciando proceso Python: {e}"

            with state_lock:
                latest_telemetry_state["simulation_status"] = {
                    "running": True,
                    "model": model,
                    "pid": self.proc.pid,
                    "step": 0,
                    "max_steps": self.max_steps,
                    "progress_pct": 0.0,
                    "elapsed_s": 0.0,
                    "message": f"Ejecutando {model}..."
                }
                latest_telemetry_state["logs"].append({
                    "timestamp": time.strftime("%H:%M:%S"),
                    "message": f"Iniciado modelo '{model}' (PID {self.proc.pid}, {self.max_steps} pasos).",
                    "level": "info"
                })

            self.thread = threading.Thread(target=self._monitor_process, daemon=True)
            self.thread.start()
            return True, f"Modelo {model} iniciado con PID {self.proc.pid}."

    def stop(self):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
                self.running = False
                with state_lock:
                    latest_telemetry_state["simulation_status"]["running"] = False
                    latest_telemetry_state["simulation_status"]["message"] = "Detenido por el usuario"
                    latest_telemetry_state["logs"].append({
                        "timestamp": time.strftime("%H:%M:%S"),
                        "message": "Simulación detenida por el usuario.",
                        "level": "warn"
                    })
                return True, "Simulación detenida correctamente."
            self.running = False
            return False, "No hay simulación activa en ejecución."

    def get_status(self):
        with self.lock:
            elapsed = round(time.time() - self.start_time, 1) if self.start_time else 0.0
            pct = round((self.current_step / max(1, self.max_steps)) * 100.0, 1) if self.max_steps else 0.0
            return {
                "running": self.running,
                "model": self.model,
                "pid": self.proc.pid if self.proc else None,
                "step": self.current_step,
                "max_steps": self.max_steps,
                "progress_pct": min(100.0, pct),
                "elapsed_s": elapsed,
                "message": "En ejecución" if self.running else "Inactivo"
            }

    def _monitor_process(self):
        last_csv_line = 0
        while self.proc and self.proc.poll() is None:
            line = self.proc.stdout.readline()
            if line:
                line_str = line.strip()
                if line_str:
                    with state_lock:
                        latest_telemetry_state["logs"].append({
                            "timestamp": time.strftime("%H:%M:%S"),
                            "message": line_str,
                            "level": "info" if "error" not in line_str.lower() and "fail" not in line_str.lower() else "error"
                        })
                        if len(latest_telemetry_state["logs"]) > 100:
                            latest_telemetry_state["logs"].pop(0)

            # Monitoreo de CSV de salida en vivo
            if self.output_csv and os.path.exists(self.output_csv):
                try:
                    with open(self.output_csv, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    if len(lines) > 1 and len(lines) != last_csv_line:
                        last_csv_line = len(lines)
                        last_row = [x.strip() for x in lines[-1].strip().split(",")]
                        if len(last_row) >= 4:
                            step_idx = int(float(last_row[0]))
                            t_sec = float(last_row[1])
                            f_sys = float(last_row[2])
                            p_net = float(last_row[3])
                            self.current_step = step_idx
                            elapsed = round(time.time() - self.start_time, 1) if self.start_time else 0.0
                            pct = round((step_idx / max(1, self.max_steps)) * 100.0, 1)

                            with state_lock:
                                latest_telemetry_state["current_step"] = step_idx
                                latest_telemetry_state["time_sec"] = t_sec
                                latest_telemetry_state["f_sys_hz"] = round(f_sys, 3)
                                latest_telemetry_state["P_net_kW"] = round(p_net, 2)
                                latest_telemetry_state["simulation_status"].update({
                                    "step": step_idx,
                                    "progress_pct": min(100.0, pct),
                                    "elapsed_s": elapsed
                                })

                                # Parseo dinámico de voltajes por columna
                                # Cabecera estándar: step, time_sec, f_sys_hz, P_net_kW, V1_pu...Vn_pu, V1_V...Vn_V
                                header = [h.strip() for h in lines[0].strip().split(",")]
                                v_pu_cols = [i for i, h in enumerate(header) if h.endswith("_pu") and h.startswith("V")]
                                v_v_cols = [i for i, h in enumerate(header) if h.endswith("_V") and h.startswith("V")]

                                if v_pu_cols and len(last_row) > max(v_pu_cols):
                                    volts_map = {}
                                    for idx, col_idx in enumerate(v_pu_cols):
                                        nid = str(idx + 1)
                                        vpu = float(last_row[col_idx])
                                        vv = float(last_row[v_v_cols[idx]]) if idx < len(v_v_cols) and len(last_row) > v_v_cols[idx] else vpu * 400.0
                                        volts_map[nid] = {"V_pu": round(vpu, 5), "V_volts": round(vv, 2)}
                                    latest_telemetry_state["latest_result"]["voltages"] = volts_map
                except Exception:
                    pass
            time.sleep(0.04)

        return_code = self.proc.returncode if self.proc else 0
        with self.lock:
            self.running = False
        with state_lock:
            latest_telemetry_state["simulation_status"]["running"] = False
            latest_telemetry_state["simulation_status"]["message"] = f"Finalizado (Exit code {return_code})"
            latest_telemetry_state["logs"].append({
                "timestamp": time.strftime("%H:%M:%S"),
                "message": f"Proceso de simulación finalizado (Código de retorno: {return_code}).",
                "level": "info" if return_code == 0 else "warn"
            })

sim_manager = SimulationProcessManager()

# ---------------------------------------------------------------------------
# Manejador HTTP API & Dashboard
# ---------------------------------------------------------------------------

class DashboardHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=GUI_DIR, **kwargs)

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path in ["/api/telemetry/live", "/api/state"]:
            with state_lock:
                copy_state = dict(latest_telemetry_state)
            self._send_json(copy_state)
            return

        elif parsed.path == "/api/cables":
            self._send_json({"cables": load_cables_catalog()})
            return

        elif parsed.path == "/api/topology":
            with state_lock:
                top_cfg = dict(latest_telemetry_state.get("topology_config", {}))
            self._send_json(top_cfg)
            return

        elif parsed.path == "/api/scenarios":
            scen_info = list_available_scenarios()
            self._send_json(scen_info)
            return

        elif parsed.path == "/api/simulation/status":
            status = sim_manager.get_status()
            self._send_json(status)
            return

        elif parsed.path == "/api/profiles":
            with state_lock:
                profiles = dict(latest_telemetry_state.get("exogenous_profiles", {}))
            self._send_json(profiles)
            return

        elif parsed.path == "/api/cosim/variables":
            with state_lock:
                vars_dict = dict(latest_telemetry_state.get("cosim_variables", {}))
            self._send_json(vars_dict)
            return

        elif parsed.path in ["/api/status", "/health"]:
            self._send_json({
                "status": "ONLINE",
                "node": "DATA (10.0.0.160)",
                "role": "Almacenamiento y Dashboard Web",
                "uptime_s": time.time(),
                "sim_running": sim_manager.running
            })
            return

        elif parsed.path == "/api/export":
            export_path = sim_manager.output_csv or os.path.abspath(os.path.join(GUI_DIR, "..", "output_data", "telemetry_monitor.csv"))
            if not os.path.exists(export_path):
                export_path = os.path.abspath(os.path.join(GUI_DIR, "..", "output_data", "telemetry_monitor_formatos_bt.csv"))

            if os.path.exists(export_path):
                with open(export_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{os.path.basename(export_path)}"')
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
                return
            else:
                self._send_json({"error": "No telemetry file yet"}, 404)
                return

        # Redirigir raiz a web_dashboard.html
        if parsed.path in ["", "/"]:
            self.send_response(302)
            self.send_header("Location", "/web_dashboard.html")
            self.end_headers()
            return

        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            req_data = json.loads(body) if body else {}
        except Exception:
            req_data = {}

        # 1. Control de Escenarios
        if parsed.path == "/api/scenarios/select":
            scenario_name = req_data.get("scenario_name", "")
            success, msg = select_active_scenario(scenario_name)
            self._send_json({"status": "success" if success else "error", "message": msg}, 200 if success else 400)
            return

        elif parsed.path == "/api/scenarios/upload":
            name = req_data.get("name", "").strip()
            capa1 = req_data.get("capa1_content", "")
            topo = req_data.get("topology_content", "")
            meteo = req_data.get("meteo_content", "")
            demanda = req_data.get("demanda_content", "")
            activate = req_data.get("activate", True)
            success, msg = save_uploaded_evaluation(name, capa1, topo, meteo, demanda, activate)
            self._send_json({"status": "success" if success else "error", "message": msg}, 200 if success else 400)
            return

        # 2. Control de Simulación
        elif parsed.path == "/api/simulation/run":
            model = req_data.get("model", "run_simulation_bt_formatos")
            steps = req_data.get("steps", 600)
            success, msg = sim_manager.start(model=model, steps=steps)
            self._send_json({"status": "success" if success else "error", "message": msg, "pid": sim_manager.proc.pid if sim_manager.proc else None})
            return

        elif parsed.path == "/api/simulation/stop":
            success, msg = sim_manager.stop()
            self._send_json({"status": "success" if success else "error", "message": msg})
            return

        # 3. Variables de Co-simulación
        elif parsed.path == "/api/cosim/variables":
            with state_lock:
                cv = latest_telemetry_state.setdefault("cosim_variables", {})
                for k in ["duration_s", "max_steps", "dt_macro_s", "solver_mode", "mesh_type", "slack_mode", "hold_mode", "zfoh_lambda", "network_profile"]:
                    if k in req_data:
                        cv[k] = req_data[k]

                # Reflejar también en claves raíz retrocompatibles
                if "hold_mode" in req_data:
                    latest_telemetry_state["hold_mode"] = req_data["hold_mode"]
                if "zfoh_lambda" in req_data:
                    latest_telemetry_state["zfoh_lambda"] = float(req_data["zfoh_lambda"])
                if "network_profile" in req_data:
                    latest_telemetry_state["network_profile"] = req_data["network_profile"]

                latest_telemetry_state["logs"].append({
                    "timestamp": time.strftime("%H:%M:%S"),
                    "message": f"Variables co-simulación aplicadas: {cv.get('solver_mode')}, {cv.get('mesh_type')}, Slack={cv.get('slack_mode')}, dt={cv.get('dt_macro_s')}s",
                    "level": "info"
                })
            self._send_json({"status": "success", "variables": cv})
            return

        # 4. Asignación de Coordenadas Geográficas a Nodos
        elif parsed.path == "/api/node/coordinates":
            node_id = str(req_data.get("node_id", ""))
            lat = req_data.get("lat")
            lon = req_data.get("lon")
            if not node_id or lat is None or lon is None:
                self._send_json({"error": "Faltan parámetros node_id, lat o lon"}, 400)
                return
            with state_lock:
                nodes = latest_telemetry_state.setdefault("topology_config", {}).setdefault("nodes", {})
                if node_id in nodes:
                    nodes[node_id]["lat"] = float(lat)
                    nodes[node_id]["lon"] = float(lon)
                    if "type" in req_data:
                        nodes[node_id]["type"] = req_data["type"]
                    if "name" in req_data:
                        nodes[node_id]["name"] = req_data["name"]
                    latest_telemetry_state["logs"].append({
                        "timestamp": time.strftime("%H:%M:%S"),
                        "message": f"Coordenadas actualizadas Nodo {node_id}: Lat={lat}, Lon={lon}",
                        "level": "info"
                    })
                    self._send_json({"status": "success", "node": nodes[node_id]})
                    return
                else:
                    nodes[node_id] = {
                        "lat": float(lat),
                        "lon": float(lon),
                        "type": req_data.get("type", "LOAD"),
                        "name": req_data.get("name", f"Nodo {node_id}"),
                        "role": req_data.get("role", "Demanda Dinámica")
                    }
                    self._send_json({"status": "success", "node": nodes[node_id]})
                    return

        # 5. Topología existente
        elif parsed.path == "/api/topology":
            with state_lock:
                top = latest_telemetry_state.setdefault("topology_config", {})
                if "v_base" in req_data:
                    top["v_base"] = float(req_data["v_base"])
                if "s_base" in req_data:
                    top["s_base"] = float(req_data["s_base"])
                if "branches" in req_data:
                    top["branches"] = req_data["branches"]
                if "nodes" in req_data:
                    top["nodes"] = req_data["nodes"]
                if "preset" in req_data:
                    top["preset"] = req_data["preset"]
                latest_telemetry_state["logs"].append({
                    "timestamp": time.strftime("%H:%M:%S"),
                    "message": f"Topología actualizada: Vb={top.get('v_base')}V, Sb={top.get('s_base')}VA, {len(top.get('branches', []))} ramas.",
                    "level": "info"
                })
            self._send_json({"status": "success", "topology": top})
            return

        elif parsed.path == "/api/profile/solar":
            with state_lock:
                prof = latest_telemetry_state.setdefault("exogenous_profiles", {}).setdefault("solar", {})
                prof.update(req_data)
                latest_telemetry_state["logs"].append({
                    "timestamp": time.strftime("%H:%M:%S"),
                    "message": f"Perfil solar asignado a Nodo {prof.get('target_node')}: G={prof.get('irradiance_w_m2')} W/m2, T={prof.get('temp_c')} °C",
                    "level": "info"
                })
            self._send_json({"status": "success", "solar": prof})
            return

        elif parsed.path == "/api/profile/wind":
            with state_lock:
                prof = latest_telemetry_state.setdefault("exogenous_profiles", {}).setdefault("wind", {})
                prof.update(req_data)
                latest_telemetry_state["logs"].append({
                    "timestamp": time.strftime("%H:%M:%S"),
                    "message": f"Perfil eólico asignado a Nodo {prof.get('target_node')}: V_w={prof.get('wind_speed_ms')} m/s",
                    "level": "info"
                })
            self._send_json({"status": "success", "wind": prof})
            return

        elif parsed.path == "/api/profile/hydro":
            with state_lock:
                prof = latest_telemetry_state.setdefault("exogenous_profiles", {}).setdefault("hydro", {})
                prof.update(req_data)
                latest_telemetry_state["logs"].append({
                    "timestamp": time.strftime("%H:%M:%S"),
                    "message": f"Perfil hidrocinético asignado a Nodo {prof.get('target_node')}: Q={prof.get('flow_rate_m3s')} m3/s",
                    "level": "info"
                })
            self._send_json({"status": "success", "hydro": prof})
            return

        elif parsed.path == "/api/config":
            with state_lock:
                if "hold_mode" in req_data:
                    latest_telemetry_state["hold_mode"] = req_data["hold_mode"]
                if "zfoh_lambda" in req_data:
                    latest_telemetry_state["zfoh_lambda"] = float(req_data["zfoh_lambda"])
                if "network_profile" in req_data:
                    latest_telemetry_state["network_profile"] = req_data["network_profile"]
            self._send_json({"status": "success", "message": "Configuración sincronizada"})
            return

        self._send_json({"error": "Ruta no encontrada"}, 404)


class ReusableThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_web_server(host="0.0.0.0", port=8000, auto_open=True):
    try:
        httpd = ReusableThreadingServer((host, port), DashboardHTTPHandler)
        url = f"http://localhost:{port}/web_dashboard.html"
        print(f" [WEB] Servidor Dashboard HTTP escuchando en {url}")
        if auto_open:
            import webbrowser
            threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        httpd.serve_forever()
    except Exception as e:
        print(f" [WEB ERROR] No se pudo iniciar servidor web en puerto {port}: {e}")


class RPiDataService:
    """
    Servicio Integrado para la Raspberry Pi DATA (10.0.0.160):
      1. Servidor Web Dashboard (HTTP en puerto 8000 para acceso desde cualquier navegador).
      2. Suscriptor ZeroMQ del Reloj Maestro (PC Central) y canales DERs P2P.
      3. Registro en tiempo real de telemetría a disco (CSV).
    """
    def __init__(
        self,
        master_host: str = "10.0.0.156",
        port_pub: int = 5556,
        web_port: int = 8000,
        der_p2p_targets: list = None,
        output_csv: str = "output_data/telemetry_monitor.csv"
    ):
        self.master_host = master_host
        self.port_pub = port_pub
        self.web_port = int(web_port)
        self.der_p2p_targets = der_p2p_targets or ["10.0.0.151:6001", "10.0.0.152:6002", "10.0.0.153:6003"]
        self.output_csv = os.path.abspath(output_csv)
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
        self.num_nodes = 8
        self.csv_initialized = False

    def _init_csv(self, n_nodes=None):
        n_count = n_nodes or self.num_nodes
        headers = ["step", "time_sec", "f_sys_hz", "P_net_kW"]
        headers += [f"V{i}_pu" for i in range(1, n_count + 1)]
        headers += [f"V{i}_V" for i in range(1, n_count + 1)]
        headers += [
            "Q_ratio_1", "Q_ratio_2", "Q_ratio_3",
            "error_Q_12", "error_Q_23", "error_V_12", "error_V_23"
        ]
        with open(self.output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

    def run(self, max_steps=None):
        print("=" * 65)
        print(" RASPBERRY PI DATA: DASHBOARD WEB + STORAGE TELEMETRIA")
        print(f" - Servidor Maestro:      tcp://{self.master_host}:{self.port_pub}")
        print(f" - Canales DERs P2P:      {self.der_p2p_targets}")
        print(f" - Dashboard Web:         http://0.0.0.0:{self.web_port}/web_dashboard.html")
        print(f" - Archivo Telemetria:    {self.output_csv}")
        print("=" * 65)

        # Iniciar servidor web HTTP en segundo plano
        web_thread = threading.Thread(target=start_web_server, kwargs={"host": "0.0.0.0", "port": self.web_port}, daemon=True)
        web_thread.start()

        self.running = True
        step_count = 0
        der_states = {}

        try:
            while self.running:
                step_count += 1
                if max_steps and step_count > max_steps:
                    print(f"\n[DATA DASHBOARD] Simulacion de {max_steps} pasos finalizada exitosamente.")
                    print(f" [WEB] El Dashboard permanece 100% activo en http://0.0.0.0:{self.web_port}/web_dashboard.html")
                    print(" Esperando nueva sesion de simulacion...\n")
                    while self.running:
                        try:
                            clock_msg = self.sub_clock.recv_json()
                            if clock_msg and clock_msg.get("step", 999) <= 2:
                                print("\n[DATA DASHBOARD] Nueva sesion de simulacion detectada. Reiniciando contador...")
                                step_count = 1
                                break
                        except zmq.Again:
                            time.sleep(0.5)
                            continue

                try:
                    clock_msg = self.sub_clock.recv_json()
                except zmq.Again:
                    continue

                step_idx = clock_msg.get("step", step_count)
                time_s = clock_msg.get("time_sec", step_idx * 0.5)
                f_sys = clock_msg.get("f_sys_hz", 60.0)
                p_net = clock_msg.get("P_net_w", 0.0) / 1000.0
                voltages = clock_msg.get("voltages", {})

                time.sleep(0.015)
                while True:
                    socks = dict(self.poller.poll(timeout=10))
                    if self.sub_ders in socks and socks[self.sub_ders] == zmq.POLLIN:
                        try:
                            der_msg = self.sub_ders.recv_json()
                            s_id = der_msg.get("sender_id")
                            if s_id:
                                der_states[s_id] = der_msg
                        except Exception:
                            break
                    else:
                        break

                q1 = der_states.get(1, {}).get("Q_ratio", 0.0)
                q2 = der_states.get(2, {}).get("Q_ratio", 0.0)
                q3 = der_states.get(3, {}).get("Q_ratio", 0.0)

                err_q_12 = abs(q1 - q2)
                err_q_23 = abs(q2 - q3)

                if not self.csv_initialized:
                    if voltages:
                        detected_max = max([int(k) for k in voltages.keys()])
                        actual_n = max(self.num_nodes, detected_max)
                    else:
                        actual_n = self.num_nodes
                    self.num_nodes = actual_n
                    self._init_csv(actual_n)
                    self.csv_initialized = True

                v_pu = [voltages.get(str(i), {}).get("V_pu", 1.0) for i in range(1, self.num_nodes + 1)]
                v_volts = [voltages.get(str(i), {}).get("V_volts", 400.0) for i in range(1, self.num_nodes + 1)]

                err_v_12 = abs(v_pu[0] - v_pu[1]) if len(v_pu) >= 2 else 0.0
                err_v_23 = abs(v_pu[1] - v_pu[2]) if len(v_pu) >= 3 else 0.0

                row = [
                    step_idx, round(time_s, 2), round(f_sys, 4), round(p_net, 2),
                    *[round(x, 5) for x in v_pu],
                    *[round(x, 2) for x in v_volts],
                    round(q1, 4), round(q2, 4), round(q3, 4),
                    round(err_q_12, 4), round(err_q_23, 4),
                    round(err_v_12, 5), round(err_v_23, 5)
                ]
                with open(self.output_csv, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(row)

                with state_lock:
                    latest_telemetry_state["current_step"] = step_idx
                    latest_telemetry_state["time_sec"] = round(time_s, 2)
                    latest_telemetry_state["f_sys_hz"] = round(f_sys, 3)
                    latest_telemetry_state["P_net_kW"] = round(p_net, 2)
                    latest_telemetry_state["latest_result"] = {
                        "step": step_idx,
                        "voltages": {
                            str(i): {
                                "V_pu": round(v_pu[i-1], 5),
                                "V_volts": round(v_volts[i-1], 2)
                            } for i in range(1, self.num_nodes + 1)
                        },
                        "network_stats": {
                            "profile": "LAN_ETHERNET",
                            "avg_delay_ms": 1.2,
                            "packet_loss_ratio": 0.0
                        }
                    }
                    latest_telemetry_state["q_ratios"] = {"1": round(q1, 4), "2": round(q2, 4), "3": round(q3, 4)}
                    latest_telemetry_state["errors"] = {
                        "err_q_12": round(err_q_12, 4),
                        "err_q_23": round(err_q_23, 4),
                        "err_v_12": round(err_v_12, 5),
                        "err_v_23": round(err_v_23, 5)
                    }
                    if step_idx % 4 == 0:
                        log_msg = f"Paso {step_idx:04d} | f={f_sys:.2f}Hz | P_net={p_net:5.1f}kW | V_min={min(v_pu):.4f}pu"
                        latest_telemetry_state["logs"].append({
                            "timestamp": time.strftime("%H:%M:%S"),
                            "message": log_msg,
                            "level": "info"
                        })
                        if len(latest_telemetry_state["logs"]) > 50:
                            latest_telemetry_state["logs"].pop(0)

                if step_idx % 2 == 0:
                    print(f"[DATA DASHBOARD] Paso {step_idx:04d} | f={f_sys:.3f}Hz | P_net={p_net:5.1f}kW | V_min={min(v_pu):.4f}pu | Web: OK")

        except KeyboardInterrupt:
            print("\nDeteniendo servicio de Dashboard y Storage...")
        finally:
            self.sub_clock.close()
            self.sub_ders.close()
            self.context.term()
            print(f"Servicio finalizado. Telemetria guardada en: {self.output_csv}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servicio Integrado RPi DATA: Dashboard + Storage + Simulación")
    parser.add_argument("--master-host", default="10.0.0.156", help="IP del PC Central")
    parser.add_argument("--port-pub", type=int, default=5556, help="Puerto PUB del reloj ZMQ")
    parser.add_argument("--web-port", type=int, default=8000, help="Puerto HTTP del Dashboard Web")
    parser.add_argument("--der-targets", nargs="*", default=["10.0.0.151:6001", "10.0.0.152:6002", "10.0.0.153:6003"], help="Canales P2P DERs")
    parser.add_argument("--output-csv", default="output_data/telemetry_monitor.csv", help="Ruta archivo CSV")
    parser.add_argument("--steps", type=int, default=None, help="Numero maximo de pasos")
    parser.add_argument("--standalone", action="store_true", help="Iniciar únicamente el servidor HTTP del Dashboard")
    args = parser.parse_args()

    if args.standalone:
        start_web_server(host="0.0.0.0", port=args.web_port)
    else:
        service = RPiDataService(
            master_host=args.master_host,
            port_pub=args.port_pub,
            web_port=args.web_port,
            der_p2p_targets=args.der_targets,
            output_csv=args.output_csv
        )
        service.run(max_steps=args.steps)
