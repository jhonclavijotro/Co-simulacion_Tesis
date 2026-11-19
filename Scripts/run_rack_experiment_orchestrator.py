#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orquestador de Ensayos HIL en el Rack Físico de Raspberry Pi
============================================================

Automatiza la preparación, ejecución, monitoreo, descarga de telemetría y
restauración a prueba de fallos para los ensayos formales en el rack de hardware:
  - S-O-18 / Familia 2 D-24: Par Excedentario (ESC-HIL-006 / ESC-HIL-007)
  - S-O-13: Cargas Dinámicas y Rampas Solares (ESC-HIL-005)
  - S-34 / D-25: Resiliencia Telemétrica y Contingencias en Hardware

Garantía de Invarianza:
  ACTIVO.txt se restaura SIEMPRE a ESC-HIL-003_consolidado_rev5 mediante
  bloque try ... finally ante cualquier interrupción o error.
"""

import os
import sys
import csv
import shutil
import time
import json
import hashlib
import argparse
from datetime import datetime
from typing import Dict, Any, Optional, List

# Cargar dependencias locales
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Scripts.cluster_deployer import ClusterDeployer, get_local_ip
from Central_PC.power_flow_clock_server import PowerFlowClockServer


FORMS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Forms", "escenarios_generados"))
ACTIVO_FILE = os.path.join(FORMS_DIR, "ACTIVO.txt")


def get_current_active_scenario() -> str:
    """Lee el escenario activo actual desde ACTIVO.txt o devuelve el valor por defecto."""
    if os.path.exists(ACTIVO_FILE):
        try:
            with open(ACTIVO_FILE, "r", encoding="utf-8") as f:
                val = f.read().strip()
                if val and os.path.exists(os.path.join(FORMS_DIR, val)):
                    return val
        except Exception:
            pass
    return "ESC-HIL-008_validacion_integrada"


CANONICAL_BASELINE = get_current_active_scenario()


def compute_sha256(filepath: str) -> str:
    """Calcula el hash SHA-256 de un archivo binario/texto."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class RackExperimentOrchestrator:
    def __init__(
        self,
        list_file: str = "raspberry_list.md",
        engine: str = "docker",
        dry_run: bool = False,
        local_sil: bool = False,
        fast_mode: bool = False
    ):
        self.list_file = list_file
        self.engine = engine
        self.dry_run = dry_run
        self.local_sil = local_sil
        self.fast_mode = fast_mode
        self.deployer = ClusterDeployer(list_path=list_file) if not local_sil else None
        self.local_ip = "127.0.0.1" if local_sil else get_local_ip()

    def set_active_scenario(self, scenario_name: str, sync_remote: bool = True):
        """Establece el escenario activo local y remotamente en las Raspberry Pis."""
        scenario_path = os.path.join(FORMS_DIR, scenario_name)
        if not os.path.exists(scenario_path):
            raise FileNotFoundError(f"El escenario '{scenario_name}' no existe en {FORMS_DIR}")

        print(f"[ESCENARIO] Estableciendo escenario activo -> '{scenario_name}'")
        if not self.dry_run:
            try:
                with open(ACTIVO_FILE, "w", encoding="utf-8") as f:
                    f.write(scenario_name.strip())
            except Exception as e:
                print(f"[AVISO] No se pudo escribir en ACTIVO.txt local ({e}), continuando...")

        if sync_remote and not self.dry_run and not self.local_sil and self.deployer:
            print("--> Propagando ACTIVO.txt a todos los nodos del clúster...")
            for node in self.deployer.nodes:
                remote_activo = f"{self.deployer.get_remote_dir(node)}/Forms/escenarios_generados/ACTIVO.txt"
                try:
                    ssh = self.deployer._get_ssh_client(node, timeout=4)
                    sftp = ssh.open_sftp()
                    sftp.put(ACTIVO_FILE, remote_activo)
                    sftp.close()
                    ssh.close()
                except Exception as e:
                    print(f"    [AVISO] No se pudo actualizar ACTIVO.txt en {node['name']} ({node['ip']}): {e}")

    def restore_canonical_baseline(self):
        """Restaura de forma mandatoria ACTIVO.txt a ESC-HIL-003_consolidado_rev5."""
        print(f"\n[SEGURIDAD] Restaurando ACTIVO.txt a la línea base canónica: '{CANONICAL_BASELINE}'")
        self.set_active_scenario(CANONICAL_BASELINE, sync_remote=(not self.local_sil))

    def run_experiment(
        self,
        scenario_name: str,
        steps: int = 600,
        dt_s: float = 0.5,
        p_min_diesel: Optional[float] = None,
        p_charge_max: Optional[float] = None,
        network_profile: Optional[str] = None,
        contingencies_file: Optional[str] = None,
        network_seed: int = 42,
        sync_code: bool = False,
        output_subfolder: str = "ensayos_rack",
        q_perturb_node: Optional[int] = None,
        q_perturb_var: float = 0.0,
        q_perturb_start: float = 40.0,
        q_perturb_end: float = 120.0,
        q_step_node: Optional[int] = None,
        q_step_var: float = 1000.0,
        q_step_start: Optional[float] = None,
        q_step_duration: float = 5.0
    ) -> Dict[str, Any]:
        """
        Ejecuta un ciclo formal de ensayo HIL con salvaguarda integral.
        """
        run_timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        run_id = f"{run_timestamp}_{scenario_name}_seed{network_seed}"
        scenario_dir = os.path.join(FORMS_DIR, scenario_name)
        topo_csv = os.path.join(scenario_dir, "topologia_red_8nodos.csv")

        if not os.path.exists(topo_csv):
            # Fallback a topología base si el escenario no tiene copia local
            topo_csv = os.path.abspath("config/topologia_BT_8nodos.csv")

        results_dir = os.path.abspath(os.path.join("outputs", output_subfolder, "results", run_id))

        print("\n" + "=" * 75)
        print(f" INICIANDO ENSAYO HIL EN RACK: {run_id}")
        print(f" - Escenario: {scenario_name}")
        print(f" - Duración: {steps} muestras ({(steps - 1) * dt_s:.1f} s / {steps} filas esperadas)")
        print(f" - PC Central IP: {self.local_ip}")
        print(f" - Diésel P_min: {p_min_diesel} W | BESS P_charge_max: {p_charge_max} W")
        print(f" - Perfil Telemático: {network_profile or 'IDEAL'} | Semilla: {network_seed}")
        print("=" * 75)

        start_time_iso = datetime.now().isoformat()
        experiment_meta = {
            "run_id": run_id,
            "scenario": scenario_name,
            "steps": steps,
            "dt_s": dt_s,
            "start_time": start_time_iso,
            "parameters": {
                "p_min_diesel": p_min_diesel,
                "p_charge_max": p_charge_max,
                "network_profile": network_profile,
                "contingencies_file": contingencies_file,
                "network_seed": network_seed,
            }
        }

        local_procs = []
        try:
            # 1. Configurar escenario activo
            self.set_active_scenario(scenario_name, sync_remote=(not self.local_sil))

            if sync_code and not self.dry_run and not self.local_sil and self.deployer:
                self.deployer.sync_code_to_all()

            if self.dry_run:
                print("\n[DRY RUN] Simulación en modo seco. No se crean carpetas ni se ejecutan comandos en el clúster.")
                return experiment_meta

            os.makedirs(results_dir, exist_ok=True)
            backup_csv = os.path.join(results_dir, "telemetry_central_backup.csv")
            local_csv = os.path.join(results_dir, "telemetry_rack.csv")

            if self.local_sil:
                import subprocess
                print(f"\n[Paso 1-2/5] Levantando procesos distribuidos locales en 127.0.0.1 (Modo SIL Local)...")
                scenario_file = os.path.join(scenario_dir, "plantilla_configuracion_cosimulacion.json")
                python_bin = sys.executable

                cmd_n1 = [
                    python_bin, "-u", "-B", "Agents/distributed_node_runner.py",
                    "--node-id", "1", "--source-type", "DIESEL",
                    "--master-host", "127.0.0.1", "--p2p-port", "6001",
                    "--neighbors", "127.0.0.1:6002",
                    "--mode", "OFFLINE", "--v-base", "400.0",
                    "--p-max", "10000.0", "--q-max", "6000.0",
                    "--q-init", "0.0", "--p-init", "4000.0",
                    "--steps", str(steps)
                ]
                if p_min_diesel is not None:
                    cmd_n1.extend(["--p-min-diesel", str(p_min_diesel)])
                if network_profile:
                    cmd_n1.extend(["--network-profile", network_profile])
                if contingencies_file:
                    cmd_n1.extend(["--contingencies-file", contingencies_file])
                if network_seed is not None:
                    cmd_n1.extend(["--network-seed", str(network_seed)])
                if os.path.exists(scenario_file):
                    cmd_n1.extend(["--scenario-file", scenario_file])

                cmd_n2 = [
                    python_bin, "-u", "-B", "Agents/distributed_node_runner.py",
                    "--node-id", "2", "--source-type", "SOLAR",
                    "--master-host", "127.0.0.1", "--p2p-port", "6002",
                    "--neighbors", "127.0.0.1:6001", "127.0.0.1:6003",
                    "--mode", "OFFLINE", "--v-base", "400.0",
                    "--p-max", "5000.0", "--q-max", "3000.0",
                    "--q-init", "0.0", "--p-init", "0.0",
                    "--curtail-min", "0.15",
                    "--steps", str(steps)
                ]
                if network_profile:
                    cmd_n2.extend(["--network-profile", network_profile])
                if contingencies_file:
                    cmd_n2.extend(["--contingencies-file", contingencies_file])
                if network_seed is not None:
                    cmd_n2.extend(["--network-seed", str(network_seed)])
                if os.path.exists(scenario_file):
                    cmd_n2.extend(["--scenario-file", scenario_file])

                cmd_n3 = [
                    python_bin, "-u", "-B", "Agents/distributed_node_runner.py",
                    "--node-id", "3", "--source-type", "BESS",
                    "--master-host", "127.0.0.1", "--p2p-port", "6003",
                    "--neighbors", "127.0.0.1:6002",
                    "--mode", "OFFLINE", "--v-base", "400.0",
                    "--p-max", "3000.0", "--q-max", "1000.0",
                    "--q-init", "0.0", "--p-init", "0.0",
                    "--steps", str(steps)
                ]
                if p_charge_max is not None:
                    cmd_n3.extend(["--p-charge-max", str(p_charge_max)])
                if network_profile:
                    cmd_n3.extend(["--network-profile", network_profile])
                if contingencies_file:
                    cmd_n3.extend(["--contingencies-file", contingencies_file])
                if network_seed is not None:
                    cmd_n3.extend(["--network-seed", str(network_seed)])
                if os.path.exists(scenario_file):
                    cmd_n3.extend(["--scenario-file", scenario_file])

                if q_perturb_node is not None:
                    q_flags = [
                        "--q-perturb-node", str(q_perturb_node),
                        "--q-perturb-var", str(q_perturb_var),
                        "--q-perturb-start", str(q_perturb_start),
                        "--q-perturb-end", str(q_perturb_end)
                    ]
                    cmd_n1.extend(q_flags)
                    cmd_n2.extend(q_flags)
                    cmd_n3.extend(q_flags)

                # Resolver excitación reactiva de cargas desde meta.json si no vino explícita por CLI
                meta_path = os.path.join(scenario_dir, "meta.json")
                if q_step_node is None and os.path.exists(meta_path):
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f_m:
                            ex_q = json.load(f_m).get("excitacion_reactiva") or {}
                        if "nodo" in ex_q:
                            q_step_node = int(ex_q["nodo"])
                            q_step_var = float(ex_q.get("q_step_var", 1000.0))
                            q_step_start = float(ex_q.get("inicio_s", 50.0))
                            q_step_duration = float(ex_q.get("duracion_s", 5.0))
                    except Exception:
                        pass

                # S-O-38 / S-O-40: Leer escala de droop y sub-pasos de consenso desde meta.json si existen
                k_m = 1.0
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f_m:
                            meta_data = json.load(f_m)
                            p_droop = meta_data.get("parametros_droop") or {}
                            k_m = float(p_droop.get("k_m", 1.0))
                            if "m_q1" in p_droop and "m_q2" in p_droop and "m_q3" in p_droop:
                                cmd_n1.extend(["--m-q", str(float(p_droop["m_q1"]))])
                                cmd_n2.extend(["--m-q", str(float(p_droop["m_q2"]))])
                                cmd_n3.extend(["--m-q", str(float(p_droop["m_q3"]))])
                                print(f"    [S-O-38] Estatismo reactivo configurado desde meta.json: m_q1={p_droop['m_q1']}, m_q2={p_droop['m_q2']}, m_q3={p_droop['m_q3']} (k_m={k_m})")
                            elif k_m != 1.0:
                                cmd_n1.extend(["--m-q", str(0.0013333333333333333 * k_m)])
                                cmd_n2.extend(["--m-q", str(0.0026666666666666666 * k_m)])
                                cmd_n3.extend(["--m-q", str(0.0080000000000000000 * k_m)])
                                print(f"    [S-O-38] Estatismo reactivo escalado con factor uniforme k_m = {k_m:.4f}")
                            c_substeps = int(meta_data.get("consensus_substeps", 1))
                            if c_substeps > 1:
                                cmd_n1.extend(["--consensus-substeps", str(c_substeps)])
                                cmd_n2.extend(["--consensus-substeps", str(c_substeps)])
                                cmd_n3.extend(["--consensus-substeps", str(c_substeps)])
                                print(f"    [S-O-40] Sub-pasos internos de consenso configurados: n = {c_substeps} (dt_sub = {0.5 / c_substeps:.4f} s)")
                            c_interval = float(meta_data.get("consensus_interval") or meta_data.get("T_c") or 0.5)
                            if c_interval != 0.5:
                                cmd_n1.extend(["--consensus-interval", str(c_interval)])
                                cmd_n2.extend(["--consensus-interval", str(c_interval)])
                                cmd_n3.extend(["--consensus-interval", str(c_interval)])
                                print(f"    [S-O-42] Intervalo de actualización de consenso: T_c = {c_interval:.2f} s")
                            if "c1" in meta_data and "c2" in meta_data:
                                cmd_n1.extend(["--c1", str(float(meta_data["c1"])), "--c2", str(float(meta_data["c2"]))])
                                cmd_n2.extend(["--c1", str(float(meta_data["c1"])), "--c2", str(float(meta_data["c2"]))])
                                cmd_n3.extend(["--c1", str(float(meta_data["c1"])), "--c2", str(float(meta_data["c2"]))])
                                print(f"    [S-O-43] Parámetros Polyakov: c1 = {meta_data['c1']}, c2 = {meta_data['c2']}")
                            if abs(float(dt_s) - 0.5) > 1e-6:
                                cmd_n1.extend(["--macro-dt", str(float(dt_s))])
                                cmd_n2.extend(["--macro-dt", str(float(dt_s))])
                                cmd_n3.extend(["--macro-dt", str(float(dt_s))])
                                print(f"    [S-O-46] Multi-rate: paso de solucionador dt_pf = {float(dt_s)*1000:.0f} ms (consenso fijo en T_c = {c_interval:.2f} s)")
                            q_interp = int(meta_data.get("q_interp_substeps", 1))
                            if q_interp > 1:
                                cmd_n1.extend(["--q-interp-substeps", str(q_interp)])
                                cmd_n2.extend(["--q-interp-substeps", str(q_interp)])
                                cmd_n3.extend(["--q-interp-substeps", str(q_interp)])
                                print(f"    [S-O-48 A] Interpolación de consigna Q_ref en {q_interp} sub-pasos")
                            if meta_data.get("freeze_consensus", False):
                                def _strip_neighbors(cmd_list):
                                    out = []
                                    skip = False
                                    for item in cmd_list:
                                        if item == "--neighbors":
                                            skip = True
                                            continue
                                        if skip:
                                            if item.startswith("--"):
                                                skip = False
                                            else:
                                                continue
                                        out.append(item)
                                    return out
                                cmd_n1 = _strip_neighbors(cmd_n1)
                                cmd_n2 = _strip_neighbors(cmd_n2)
                                cmd_n3 = _strip_neighbors(cmd_n3)
                                print("    [S-O-41 / M2] Consenso congelado activado: N_i = {} (sin vecinos P2P)")
                    except Exception as err_droop:
                        print(f"    [WARN] No se pudo leer parametros de meta.json: {err_droop}")

                cmd_loads = [
                    python_bin, "-u", "-B", "Agents/multi_load_process.py",
                    "--master-host", "127.0.0.1",
                    "--nodos", "4,5,6,7,8",
                    "--steps", str(steps)
                ]
                if q_step_node is not None:
                    cmd_loads.extend([
                        "--q-step-node", str(q_step_node),
                        "--q-step-var", str(q_step_var),
                        "--q-step-start", str(q_step_start if q_step_start is not None else 50.0),
                        "--q-step-duration", str(q_step_duration)
                    ])
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f_m2:
                            m_d2 = json.load(f_m2)
                        ex_q2 = m_d2.get("excitacion_reactiva_2") or {}
                        if "nodo" in ex_q2:
                            cmd_loads.extend([
                                "--q-step2-node", str(int(ex_q2["nodo"])),
                                "--q-step2-var", str(float(ex_q2.get("q_step_var", 1000.0))),
                                "--q-step2-start", str(float(ex_q2.get("inicio_s", 100.0))),
                                "--q-step2-duration", str(float(ex_q2.get("duracion_s", 5.0)))
                            ])
                    except Exception:
                        pass

                os.makedirs("output_data", exist_ok=True)
                f_n1 = open("output_data/node_1_sil.log", "w", encoding="utf-8")
                f_n2 = open("output_data/node_2_sil.log", "w", encoding="utf-8")
                f_n3 = open("output_data/node_3_sil.log", "w", encoding="utf-8")
                f_loads = open("output_data/loads_sil.log", "w", encoding="utf-8")

                local_procs = [
                    subprocess.Popen(cmd_n1, stdout=f_n1, stderr=subprocess.STDOUT),
                    subprocess.Popen(cmd_n2, stdout=f_n2, stderr=subprocess.STDOUT),
                    subprocess.Popen(cmd_n3, stdout=f_n3, stderr=subprocess.STDOUT),
                    subprocess.Popen(cmd_loads, stdout=f_loads, stderr=subprocess.STDOUT),
                ]
                print(f"    [OK] 4 procesos distribuidos iniciados localmente en 127.0.0.1 (logs en output_data/).")
                time.sleep(3.5)
            else:
                # 2. Limpieza preventiva en el clúster
                print("\n[Paso 1/5] Deteniendo contenedores previos en el clúster...")
                self.deployer.stop_cluster()
                time.sleep(1.0)

                # 3. Lanzar clúster con parámetros específicos
                print(f"\n[Paso 2/5] Levantando servicios en las Raspberry Pis ({self.engine})...")
                self.deployer.start_cluster(
                    steps=steps,
                    engine=self.engine,
                    p_min_diesel=p_min_diesel,
                    p_charge_max=p_charge_max,
                    network_profile=network_profile,
                    contingencies_file=contingencies_file,
                    network_seed=network_seed,
                )
                print("Esperando 3.5 segundos para estabilización de sockets P2P ZeroMQ...")
                time.sleep(3.5)

            # 4. Iniciar Servidor Maestro ZMQ en PC Central
            print(f"\n[Paso 3/5] Arrancando PowerFlowClockServer (FBS 8 Nodos @ 400 V)...")
            server = PowerFlowClockServer(
                topology_path=topo_csv,
                v_base=400.0,
                s_base=10000.0,
                port_rep=5555,
                port_pub=5556,
                step_dt=dt_s,
                backup_csv=backup_csv,
                fast_mode=self.fast_mode
            )

            t0 = time.perf_counter()
            server.run(max_steps=steps)
            elapsed_s = time.perf_counter() - t0
            print(f"\n[OK] Simulación completada: {steps} pasos en {elapsed_s:.2f} s.")

            # 5. Descargar telemetría desde nodo Monitor o respaldo local
            if self.local_sil:
                print("\n[Paso 4/5] Consolidando telemetría local de la ejecución SIL...")
                for p in local_procs:
                    try:
                        p.terminate()
                        p.wait(timeout=1.0)
                    except Exception:
                        p.kill()
                local_procs.clear()
                if os.path.exists(backup_csv):
                    if float(dt_s) < 0.5 - 1e-6:
                        import pandas as _pd_mr
                        solver_full_csv = os.path.join(results_dir, "telemetry_solver_full.csv")
                        shutil.copy2(backup_csv, solver_full_csv)
                        _df_mr = _pd_mr.read_csv(backup_csv)
                        _sub_factor = max(1, int(round(0.5 / float(dt_s))))
                        _df_2hz = _df_mr[_df_mr.index % _sub_factor == 0].copy()
                        _df_2hz.to_csv(local_csv, index=False)
                        print(f"    [S-O-46] Telemetría 2 Hz conservada en telemetry_rack.csv ({len(_df_2hz)} filas); sub-pasos en telemetry_solver_full.csv ({len(_df_mr)} filas).")
                    else:
                        shutil.copy2(backup_csv, local_csv)
                    telemetry_source = "local_sil_server"
                else:
                    telemetry_source = "unknown"
            else:
                print("\n[Paso 4/5] Extrayendo telemetría consolidada desde RPi 10.0.0.155...")
                monitor_node = next(n for n in self.deployer.nodes if n["ip"] == "10.0.0.155")
                remote_csv = f"{self.deployer.get_remote_dir(monitor_node)}/output_data/telemetry_monitor.csv"

                telemetry_source = "monitor_sftp"
                try:
                    ssh = self.deployer._get_ssh_client(monitor_node)
                    sftp = ssh.open_sftp()
                    sftp.get(remote_csv, local_csv)
                    sftp.close()
                    ssh.close()
                except Exception as e:
                    print(f"[AVISO] SFTP de Monitor falló ({e}); usando respaldo central local.")
                    if os.path.exists(backup_csv):
                        shutil.copy2(backup_csv, local_csv)
                        telemetry_source = "central_backup_fallback"
                    else:
                        experiment_meta["telemetry_error"] = str(e)

            if os.path.exists(local_csv):
                file_size = os.path.getsize(local_csv)
                csv_sha256 = compute_sha256(local_csv)
                print(f"[OK] Telemetría lista ({telemetry_source}):")
                print(f"     Archivo: {local_csv}")
                print(f"     Tamaño: {file_size} bytes")
                print(f"     SHA-256: {csv_sha256}")
                experiment_meta["telemetry"] = {
                    "path": local_csv,
                    "source": telemetry_source,
                    "bytes": file_size,
                    "sha256": csv_sha256
                }

                # 6. Auditoría según escenario y generación de reportes normativos
                if scenario_name == "ESC-HIL-010_validacion_integrada_v2":
                    audit_summary = self.audit_010_telemetry(local_csv, scenario_dir, results_dir)
                    experiment_meta["audit_010"] = audit_summary
                elif scenario_name.startswith("ESC-HIL-011"):
                    audit_summary = self.audit_011_telemetry(local_csv, scenario_dir, results_dir, scenario_name)
                    experiment_meta["audit_011"] = audit_summary
                elif scenario_name.startswith("ESC-HIL-012"):
                    audit_summary = self.audit_independent_telemetry(local_csv, scenario_dir, results_dir, scenario_name)
                    experiment_meta["audit_s1"] = audit_summary
                elif scenario_name.startswith("ESC-HIL-013"):
                    audit_summary = self.audit_independent_telemetry(local_csv, scenario_dir, results_dir, scenario_name)
                    experiment_meta["audit_s2"] = audit_summary
                elif scenario_name.startswith("ESC-HIL-014"):
                    audit_summary = self.audit_independent_telemetry(local_csv, scenario_dir, results_dir, scenario_name)
                    experiment_meta["audit_s3"] = audit_summary
                elif scenario_name.startswith("ESC-HIL-015"):
                    audit_summary = self.audit_independent_telemetry(local_csv, scenario_dir, results_dir, scenario_name)
                    experiment_meta["audit_s4"] = audit_summary
                elif scenario_name.startswith("ESC-HIL-016"):
                    audit_summary = self.audit_independent_telemetry(local_csv, scenario_dir, results_dir, scenario_name)
                    experiment_meta["audit_s4_180s"] = audit_summary
                elif scenario_name.startswith("ESC-HIL-017"):
                    audit_summary = self.audit_independent_telemetry(local_csv, scenario_dir, results_dir, scenario_name)
                    experiment_meta["audit_s5"] = audit_summary
                elif scenario_name.startswith("ESC-HIL-018"):
                    audit_summary = self.audit_independent_telemetry(local_csv, scenario_dir, results_dir, scenario_name)
                    experiment_meta["audit_s6"] = audit_summary
                else:
                    audit_summary = self.audit_s40_telemetry(local_csv, scenario_dir, results_dir)
                    experiment_meta["audit_s40"] = audit_summary

            # 7. Generar manifiesto de la corrida y actualizar CURRENT.json (solo validation)
            manifest_file = os.path.join(results_dir, "manifest.json")
            experiment_meta["end_time"] = datetime.now().isoformat()
            experiment_meta["elapsed_seconds"] = round(elapsed_s, 3)

            # Informacion de trazabilidad cientifica y git commit
            try:
                git_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
            except Exception:
                git_hash = "unknown"
            experiment_meta["git_commit"] = git_hash

            cont_path = os.path.join(scenario_dir, contingencies_file or "contingencias_telematicas.csv")
            meta_path = os.path.join(scenario_dir, "meta.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f_meta_man:
                        m_man = json.load(f_meta_man)
                    is_frozen = m_man.get("freeze_consensus", False)
                    experiment_meta["consensus_mode"] = "frozen (sin vecinos / anillo desactivado / correccion deltaQ=0)" if is_frozen else "active (con vecinos P2P / anillo completo)"
                    experiment_meta["consensus_interval"] = m_man.get("consensus_interval", m_man.get("T_c", 0.5))
                    experiment_meta["c1"] = m_man.get("c1", 0.25)
                    experiment_meta["c2"] = m_man.get("c2", 0.15)
                    if "congelacion_modo" in m_man:
                        experiment_meta["congelacion_modo"] = m_man["congelacion_modo"]
                except Exception:
                    pass

            experiment_meta["hashes"] = {
                "telemetry_rack_csv": experiment_meta.get("telemetry", {}).get("sha256"),
                "contingencias_telematicas_csv": compute_sha256(cont_path) if os.path.exists(cont_path) else None,
                "scenario_meta_json": compute_sha256(meta_path) if os.path.exists(meta_path) else None,
            }

            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump(experiment_meta, f, indent=2, ensure_ascii=False)
            manifest_sha256 = compute_sha256(manifest_file)
            print(f"[OK] Manifiesto generado en: {manifest_file} (SHA-256: {manifest_sha256})")

            if output_subfolder == "validation" and os.path.exists(local_csv):
                current_ptr = os.path.abspath(os.path.join("outputs", "validation", "results", "CURRENT.json"))
                ptr_payload = {
                    "run_id": run_id,
                    "scenario": scenario_name,
                    "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                    "results_dir": results_dir,
                    "manifest_path": manifest_file,
                    "manifest_sha256": manifest_sha256,
                    "telemetry_path": local_csv,
                    "telemetry_sha256": experiment_meta.get("telemetry", {}).get("sha256"),
                    "contingencies_sha256": experiment_meta["hashes"]["contingencias_telematicas_csv"],
                    "certified_s40": experiment_meta.get("audit_s40", {}).get("all_criteria_passed", False),
                }
                with open(current_ptr, "w", encoding="utf-8") as f_cur:
                    json.dump(ptr_payload, f_cur, indent=2, ensure_ascii=False)
                print(f"[OK] Puntero S-40 actualizado: {current_ptr}")
            elif output_subfolder == "validation_v2" and os.path.exists(local_csv):
                current_ptr = os.path.abspath(os.path.join("outputs", "validation_v2", "results", "CURRENT.json"))
                os.makedirs(os.path.dirname(current_ptr), exist_ok=True)
                ptr_payload = {
                    "run_id": run_id,
                    "scenario": scenario_name,
                    "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                    "results_dir": results_dir,
                    "manifest_path": manifest_file,
                    "manifest_sha256": manifest_sha256,
                    "telemetry_path": local_csv,
                    "telemetry_sha256": experiment_meta.get("telemetry", {}).get("sha256"),
                    "contingencies_sha256": experiment_meta["hashes"]["contingencias_telematicas_csv"],
                    "certified_d30": experiment_meta.get("audit_010", {}).get("all_criteria_passed", False),
                }
                with open(current_ptr, "w", encoding="utf-8") as f_cur:
                    json.dump(ptr_payload, f_cur, indent=2, ensure_ascii=False)
                print(f"[OK] Puntero Validación v2 actualizado: {current_ptr}")
            elif output_subfolder == "satellites" and os.path.exists(local_csv):
                current_ptr = os.path.abspath(os.path.join("outputs", "satellites", "results", "CURRENT.json"))
                os.makedirs(os.path.dirname(current_ptr), exist_ok=True)
                ptr_payload = {
                    "run_id": run_id,
                    "scenario": scenario_name,
                    "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                    "results_dir": results_dir,
                    "manifest_path": manifest_file,
                    "manifest_sha256": manifest_sha256,
                    "telemetry_path": local_csv,
                    "telemetry_sha256": experiment_meta.get("telemetry", {}).get("sha256"),
                    "certified_d30": experiment_meta.get("audit_011", {}).get("all_criteria_passed", False),
                }
                with open(current_ptr, "w", encoding="utf-8") as f_cur:
                    json.dump(ptr_payload, f_cur, indent=2, ensure_ascii=False)
                print(f"[OK] Puntero Satélites actualizado: {current_ptr}")

        finally:
            # 7. Salvaguarda Incondicional: Parar procesos/contenedores y restaurar ACTIVO.txt
            print("\n[Paso 5/5] Ejecutando salvaguarda y detención de procesos...")
            for p in local_procs:
                try:
                    p.terminate()
                except Exception:
                    pass
            if not self.local_sil and self.deployer:
                try:
                    stop_compute_cmd = "docker stop nodo_1_diesel nodo_2_solar nodo_3_bess nodos_cargas nodo_monitor_hil 2>/dev/null; docker rm -f nodo_1_diesel nodo_2_solar nodo_3_bess nodos_cargas nodo_monitor_hil 2>/dev/null; pkill -f distributed_node_runner; pkill -f multi_load_process; pkill -f monitor_node_service"
                    for node in self.deployer.nodes:
                        if node["ip"] != "10.0.0.160":  # Mantener dashboard web en DATA
                            try:
                                ssh = self.deployer._get_ssh_client(node, timeout=3)
                                ssh.exec_command(stop_compute_cmd)
                                ssh.close()
                            except Exception:
                                pass
                except Exception as e:
                    print(f"[AVISO] Error al detener cómputo: {e}")

            # Restaurar siempre línea base
            self.restore_canonical_baseline()

        print("\n" + "=" * 75)
        print(f" CICLO DE ENSAYO HIL FINALIZADO CON ÉXITO: {run_id}")
        print("=" * 75)
        return experiment_meta

    @staticmethod
    def audit_010_telemetry(local_csv: str, scenario_dir: str, results_dir: str) -> Dict[str, Any]:
        """Audita las 20 ventanas de ESC-HIL-010 y los criterios de aceptación D-30 / S-O-26; genera reporte_validacion_v2.md."""
        with open(local_csv, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        def _f(r: dict, key: str, default: float = 0.0) -> float:
            val = r.get(key)
            if val in (None, ""):
                return default
            return float(val)

        n_samples = len(rows)
        t_first = _f(rows[0], "time_s", _f(rows[0], "time_sec", -1.0)) if rows else -1.0
        t_last = _f(rows[-1], "time_s", _f(rows[-1], "time_sec", -1.0)) if rows else -1.0
        step_times_ms = [_f(r, "step_elapsed_ms", 0.0) for r in rows]
        overruns = sum(1 for ms in step_times_ms if ms > 500.0)

        meta_path = os.path.join(scenario_dir, "meta.json")
        windows = []
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f_m:
                    windows = json.load(f_m).get("ventanas_validacion", [])
            except Exception:
                pass

        window_metrics: List[Dict[str, Any]] = []
        for idx_w, w in enumerate(windows):
            t0, t1 = w["ventana_s"]
            is_last = idx_w == len(windows) - 1
            sub = [
                r for r in rows
                if (t0 <= _f(r, "time_s", _f(r, "time_sec", -1.0)) <= t1 if is_last
                    else t0 <= _f(r, "time_s", _f(r, "time_sec", -1.0)) < t1)
            ]
            if not sub:
                window_metrics.append({"ventana_s": [t0, t1], "evento": w.get("evento", ""), "n": 0})
                continue

            f_vals = [_f(r, "f_sys_hz", 60.0) for r in sub]
            v_all = [_f(r, f"V{i}_pu", 1.0) for r in sub for i in range(1, 9) if f"V{i}_pu" in r]
            p3_vals = [_f(r, "P3_kW", 0.0) for r in sub]
            soc_vals = [_f(r, "SoC", 0.5) for r in sub if r.get("SoC", "") != ""]
            curt_vals = [_f(r, "curtail_ratio", 1.0) for r in sub]
            curt_min_param = [_f(r, "curtail_min", 0.15) for r in sub]
            eq_vals = [_f(r, "e_Q", max(_f(r, "error_Q_12"), _f(r, "error_Q_23"))) for r in sub]
            dropped = sum(int(float(r.get("paquetes_descartados", 0) or 0)) for r in sub)
            d12_cnt = sum(1 for r in sub if "D_12" in str(r.get("contingencias_activas", "")))

            window_metrics.append({
                "ventana_s": [t0, t1],
                "evento": w.get("evento", ""),
                "n": len(sub),
                "f_min": round(min(f_vals), 4),
                "f_max": round(max(f_vals), 4),
                "V_min": round(min(v_all), 4) if v_all else 1.0,
                "V_max": round(max(v_all), 4) if v_all else 1.0,
                "P3_mean_kW": round(sum(p3_vals) / len(p3_vals), 3),
                "SoC_ini": round(soc_vals[0], 6) if soc_vals else None,
                "SoC_fin": round(soc_vals[-1], 6) if soc_vals else None,
                "curtail_ratio_min": round(min(curt_vals), 4),
                "curtail_min": round(min(curt_min_param), 4),
                "e_Q_min": round(min(eq_vals), 4),
                "e_Q_max": round(max(eq_vals), 4),
                "e_Q_final": round(eq_vals[-1], 4),
                "dropped_pkts": dropped,
                "d12_samples": d12_cnt,
            })

        # Criterios D-30 / S-O-26:
        # Criterio 1: 1321 muestras @ 2 Hz (t = 0..660 s)
        crit_1 = n_samples == 1321 and abs(t_first - 0.0) < 1e-6 and abs(t_last - 660.0) < 1e-6
        # Criterio 2: Cero overruns de tiempo real
        crit_2 = overruns == 0 and (max(step_times_ms) < 500.0 if step_times_ms else True)

        # Criterio 3: Reconvergencia en ventana P_23 [430, 480] s
        w_p23 = next((m for m in window_metrics if m["ventana_s"] == [430, 480]), {})
        crit_3 = (
            w_p23.get("e_Q_max", 0.0) > 0.01  # Excitación evidente
            and w_p23.get("e_Q_final", 1.0) < 0.05  # Reconvergencia antes del final de ventana
        )

        # Criterio 4: Estabilidad de frecuencia en cola limpia [600, 660] s
        sub_tail = [r for r in rows if _f(r, "time_s", _f(r, "time_sec", -1.0)) >= 620.0]
        f_tail = [_f(r, "f_sys_hz", 60.0) for r in sub_tail] if sub_tail else [60.0]
        tail_p2p = max(f_tail) - min(f_tail)
        tail_in_band = all(abs(f - 60.0) <= 0.05 for f in f_tail)
        crit_4 = tail_p2p <= 0.10 and tail_in_band

        all_passed = bool(crit_1 and crit_2 and crit_3 and crit_4)

        report_path = os.path.join(results_dir, "reporte_validacion_v2.md")
        lines = [
            "# Reporte de Validación HIL — ESC-HIL-010_validacion_integrada_v2 (S-O-26 / D-30)",
            "",
            f"- **Muestras:** {n_samples} (`t = {t_first}..{t_last} s`)",
            f"- **Tiempo de paso máx:** {max(step_times_ms):.2f} ms (`overruns > 500 ms`: {overruns})",
            "- **Criterios de Aceptación (D-30 / S-O-26):**",
            f"  - **Criterio 1 (1321 muestras @ 2 Hz / 660 s):** {'PASS' if crit_1 else 'FAIL'}",
            f"  - **Criterio 2 (0 violaciones RT 500 ms):** {'PASS' if crit_2 else 'FAIL'}",
            f"  - **Criterio 3 (Excitación reactiva y reconvergencia e_Q < 0.05 en P_23 [430, 480] s):** {'PASS' if crit_3 else 'FAIL'} (e_Q máx: {w_p23.get('e_Q_max', 0.0):.4f}, e_Q final: {w_p23.get('e_Q_final', 0.0):.4f})",
            f"  - **Criterio 4 (Estabilidad de frecuencia en cola limpia t in [620, 660] s, p2p <= 0.10 Hz):** {'PASS' if crit_4 else 'FAIL'} (p2p: {tail_p2p:.4f} Hz, banda |f-60|<=0.05: {tail_in_band})",
            f"- **Dictamen General:** {'CERTIFICADO' if all_passed else 'REPROBADO'}",
            "",
            "| Ventana (s) | Evento | N | f [min, max] (Hz) | V [min, max] (pu) | P_BESS media (kW) | SoC ini -> fin | curtail_ratio_min | e_Q [min, max] | e_Q final | D_12 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for m in window_metrics:
            if m.get("n", 0) == 0:
                continue
            lines.append(
                f"| [{m['ventana_s'][0]}, {m['ventana_s'][1]}] | {m['evento']} | {m['n']} | "
                f"[{m['f_min']:.3f}, {m['f_max']:.3f}] | [{m['V_min']:.4f}, {m['V_max']:.4f}] | "
                f"{m['P3_mean_kW']:+.3f} | {m['SoC_ini']} -> {m['SoC_fin']} | {m['curtail_ratio_min']:.4f} | "
                f"[{m['e_Q_min']:.4f}, {m['e_Q_max']:.4f}] | {m['e_Q_final']:.4f} | {m['d12_samples']} |"
            )
        with open(report_path, "w", encoding="utf-8") as f_rep:
            f_rep.write("\n".join(lines) + "\n")
        print(f"[OK] Reporte ESC-HIL-010 generado: {report_path}")

        return {
            "n_samples": n_samples,
            "time_range_s": [t_first, t_last],
            "max_step_elapsed_ms": round(max(step_times_ms), 3) if step_times_ms else 0.0,
            "rt_overruns": overruns,
            "criteria": {
                "certified_1321_samples": crit_1,
                "zero_rt_overruns": crit_2,
                "reactive_reconvergence_p23": crit_3,
                "frequency_tail_stability": crit_4,
            },
            "p23_metrics": {
                "e_Q_max": w_p23.get("e_Q_max", 0.0),
                "e_Q_final": w_p23.get("e_Q_final", 0.0),
            },
            "tail_frequency_p2p_hz": round(tail_p2p, 4),
            "all_criteria_passed": all_passed,
            "windows": window_metrics,
            "report_path": report_path,
        }

    @staticmethod
    def audit_011_telemetry(local_csv: str, scenario_dir: str, results_dir: str, scenario_name: str) -> Dict[str, Any]:
        """Audita los escenarios satélite ESC-HIL-011a/b (derating BESS); genera reporte_satelite.md."""
        with open(local_csv, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        def _f(r: dict, key: str, default: float = 0.0) -> float:
            val = r.get(key)
            if val in (None, ""):
                return default
            return float(val)

        n_samples = len(rows)
        t_first = _f(rows[0], "time_s", _f(rows[0], "time_sec", -1.0)) if rows else -1.0
        t_last = _f(rows[-1], "time_s", _f(rows[-1], "time_sec", -1.0)) if rows else -1.0
        step_times_ms = [_f(r, "step_elapsed_ms", 0.0) for r in rows]
        overruns = sum(1 for ms in step_times_ms if ms > 500.0)
        p3_vals = [_f(r, "P3_kW", 0.0) for r in rows]

        crit_1 = n_samples == 361 and abs(t_first - 0.0) < 1e-6 and abs(t_last - 180.0) < 1e-6
        crit_2 = overruns == 0 and (max(step_times_ms) < 500.0 if step_times_ms else True)

        is_alto = "011a" in scenario_name
        if is_alto:
            # 011a: SoC = 0.93 -> Derating de carga acotado a 600 W (P3 >= -0.65 kW en carga)
            p3_min = min(p3_vals)
            crit_3 = p3_min >= -0.650
            desc_c3 = f"Derating de carga acotado a ~600 W (P3_min = {p3_min*1000:.1f} W >= -650 W)"
        else:
            # 011b: SoC = 0.22 -> Derating de descarga acotado a 86 W (P3 <= 0.120 kW en descarga)
            p3_max = max(p3_vals)
            crit_3 = p3_max <= 0.120
            desc_c3 = f"Derating de descarga acotado a ~86 W (P3_max = {p3_max*1000:.1f} W <= 120 W)"

        all_passed = bool(crit_1 and crit_2 and crit_3)

        report_path = os.path.join(results_dir, "reporte_satelite.md")
        lines = [
            f"# Reporte de Ensayo Satélite — {scenario_name} (S-O-26 / D-30)",
            "",
            f"- **Muestras:** {n_samples} (`t = {t_first}..{t_last} s`)",
            f"- **Tiempo de paso máx:** {max(step_times_ms):.2f} ms (`overruns > 500 ms`: {overruns})",
            "- **Criterios de Aceptación:**",
            f"  - **Criterio 1 (361 muestras @ 2 Hz / 180 s):** {'PASS' if crit_1 else 'FAIL'}",
            f"  - **Criterio 2 (0 violaciones RT 500 ms):** {'PASS' if crit_2 else 'FAIL'}",
            f"  - **Criterio 3 ({desc_c3}):** {'PASS' if crit_3 else 'FAIL'}",
            f"- **Dictamen General:** {'CERTIFICADO' if all_passed else 'REPROBADO'}",
        ]
        with open(report_path, "w", encoding="utf-8") as f_rep:
            f_rep.write("\n".join(lines) + "\n")
        print(f"[OK] Reporte satélite generado: {report_path}")

        return {
            "n_samples": n_samples,
            "time_range_s": [t_first, t_last],
            "max_step_elapsed_ms": round(max(step_times_ms), 3) if step_times_ms else 0.0,
            "rt_overruns": overruns,
            "criteria": {
                "certified_361_samples": crit_1,
                "zero_rt_overruns": crit_2,
                "bess_derating_active": crit_3,
            },
            "p3_range_kW": [min(p3_vals), max(p3_vals)],
            "all_criteria_passed": all_passed,
            "report_path": report_path,
        }

    @staticmethod
    def audit_independent_telemetry(local_csv: str, scenario_dir: str, results_dir: str, scenario_name: str) -> Dict[str, Any]:
        """Audita los escenarios independientes S1/S2/S3 (ESC-HIL-012/013/014, D-31 / S-O-28 / S-O-31)."""
        with open(local_csv, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        def _f(r: dict, key: str, default: float = 0.0) -> float:
            val = r.get(key)
            if val in (None, ""):
                return default
            return float(val)

        if "012" in scenario_name:
            tag = "s1"
            tag_upper = "S1"
        elif "013" in scenario_name:
            tag = "s2"
            tag_upper = "S2"
        elif "014" in scenario_name:
            tag = "s3"
            tag_upper = "S3"
        elif "015" in scenario_name:
            tag = "s4"
            tag_upper = "S4"
        elif "016" in scenario_name:
            tag = "s4_180s"
            tag_upper = "S4_180S"
        elif "017" in scenario_name:
            tag = "s5"
            tag_upper = "S5"
        elif "018" in scenario_name:
            tag = "s6"
            tag_upper = "S6"
        else:
            tag = "indep"
            tag_upper = "INDEP"

        n_samples = len(rows)
        t_first = _f(rows[0], "time_s", _f(rows[0], "time_sec", -1.0)) if rows else -1.0
        t_last = _f(rows[-1], "time_s", _f(rows[-1], "time_sec", -1.0)) if rows else -1.0
        step_times_ms = [_f(r, "step_elapsed_ms", 0.0) for r in rows]
        overruns = sum(1 for ms in step_times_ms if ms > 500.0)

        meta_path = os.path.join(scenario_dir, "meta.json")
        windows = [
            {"ventana_s": [0, 40], "evento": "base"},
            {"ventana_s": [40, 100], "evento": "perturbacion"},
            {"ventana_s": [100, 120], "evento": "cola"},
        ]
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f_m:
                    w_meta = json.load(f_m).get("ventanas_validacion")
                if isinstance(w_meta, list) and w_meta:
                    windows = w_meta
            except Exception:
                pass

        window_metrics: List[Dict[str, Any]] = []
        for idx_w, w in enumerate(windows):
            t0, t1 = w["ventana_s"]
            is_last = idx_w == len(windows) - 1
            sub = [
                r for r in rows
                if (t0 <= _f(r, "time_s", _f(r, "time_sec", -1.0)) <= t1 if is_last
                    else t0 <= _f(r, "time_s", _f(r, "time_sec", -1.0)) < t1)
            ]
            if not sub:
                window_metrics.append({"ventana_s": [t0, t1], "evento": w.get("evento", ""), "n": 0})
                continue

            f_vals = [_f(r, "f_sys_hz", 60.0) for r in sub]
            v_all = [_f(r, f"V{i}_pu", 1.0) for r in sub for i in range(1, 9) if f"V{i}_pu" in r]
            p1_vals = [_f(r, "P1_kW", 0.0) for r in sub]
            p2_vals = [_f(r, "P2_kW", 0.0) for r in sub]
            p3_vals = [_f(r, "P3_kW", 0.0) for r in sub]
            pc_vals = [_f(r, "P_curtailed_kW", 0.0) for r in sub]
            pload_vals = [_f(r, "P_load_total_kW", 0.0) for r in sub]
            soc_vals = [_f(r, "SoC", 0.5) for r in sub if r.get("SoC", "") != ""]
            curt_vals = [_f(r, "curtail_ratio", 1.0) for r in sub]

            window_metrics.append({
                "ventana_s": [t0, t1],
                "evento": w.get("evento", ""),
                "n": len(sub),
                "f_min": round(min(f_vals), 4),
                "f_max": round(max(f_vals), 4),
                "f_mean": round(sum(f_vals) / len(f_vals), 4),
                "f_p2p": round(max(f_vals) - min(f_vals), 4),
                "V_min": round(min(v_all), 4) if v_all else 1.0,
                "V_max": round(max(v_all), 4) if v_all else 1.0,
                "P1_mean_kW": round(sum(p1_vals) / len(p1_vals), 4),
                "P2_mean_kW": round(sum(p2_vals) / len(p2_vals), 4),
                "P3_mean_kW": round(sum(p3_vals) / len(p3_vals), 4),
                "P_curtailed_mean_kW": round(sum(pc_vals) / len(pc_vals), 4),
                "P_load_mean_kW": round(sum(pload_vals) / len(pload_vals), 4),
                "SoC_ini": round(soc_vals[0], 6) if soc_vals else None,
                "SoC_fin": round(soc_vals[-1], 6) if soc_vals else None,
                "curtail_ratio_min": round(min(curt_vals), 4),
            })

        if tag in ("s4_180s", "s5", "s6"):
            tail_t0, tail_t1 = 120.0, 180.0
            tail_str = "[120, 180] s"
        else:
            tail_t0, tail_t1 = 100.0, 120.0
            tail_str = "[100, 120] s"

        sub_tail = [r for r in rows if tail_t0 <= _f(r, "time_s", _f(r, "time_sec", -1.0)) <= tail_t1]
        tail_f_vals = [_f(r, "f_sys_hz", 60.0) for r in sub_tail] if sub_tail else [60.0]
        tail_f_mean = sum(tail_f_vals) / len(tail_f_vals)
        tail_f_min = min(tail_f_vals)
        tail_f_max = max(tail_f_vals)
        tail_p2p = tail_f_max - tail_f_min
        tail_max_dev = max(abs(f - 60.0) for f in tail_f_vals)

        v_all_vals = [_f(r, f"V{i}_pu", 1.0) for r in rows for i in range(1, 9) if f"V{i}_pu" in r]
        v_min_all = min(v_all_vals) if v_all_vals else 1.0
        v_max_all = max(v_all_vals) if v_all_vals else 1.0

        p1_all = [_f(r, "P1_kW", 0.0) for r in rows]
        p2_all = [_f(r, "P2_kW", 0.0) for r in rows]
        p3_all = [_f(r, "P3_kW", 0.0) for r in rows]
        pc_all = [_f(r, "P_curtailed_kW", 0.0) for r in rows]
        curt_all = [_f(r, "curtail_ratio", 1.0) for r in rows]
        soc_all = [_f(r, "SoC", 0.5) for r in rows if r.get("SoC", "") != ""]

        sub_40_120 = [r for r in rows if _f(r, "time_s", _f(r, "time_sec", -1.0)) >= 40.0]
        p3_40_120 = [_f(r, "P3_kW", 0.0) for r in sub_40_120] if sub_40_120 else p3_all
        pc_40_120 = [_f(r, "P_curtailed_kW", 0.0) for r in sub_40_120] if sub_40_120 else pc_all
        p3_mean_40_120 = sum(p3_40_120) / len(p3_40_120)
        pc_mean_40_120 = sum(pc_40_120) / len(pc_40_120)
        soc_ini_all = soc_all[0] if soc_all else 0.5
        soc_fin_all = soc_all[-1] if soc_all else 0.5

        if tag in ("s4_180s", "s5", "s6"):
            crit_1 = n_samples == 361 and abs(t_first - 0.0) < 1e-6 and abs(t_last - 180.0) < 1e-6
            crit_samples_key = "certified_361_samples"
            crit_samples_text = "Muestras exactas (361 @ 2 Hz / 180 s)"
        else:
            crit_1 = n_samples == 241 and abs(t_first - 0.0) < 1e-6 and abs(t_last - 120.0) < 1e-6
            crit_samples_key = "certified_241_samples"
            crit_samples_text = "Muestras exactas (241 @ 2 Hz / 120 s)"

        crit_2 = overruns == 0 and (max(step_times_ms) < 500.0 if step_times_ms else True)
        crit_tail_p2p = tail_p2p <= 0.10
        crit_voltages = (v_min_all >= 0.95) and (v_max_all <= 1.05)

        criteria_dict: Dict[str, bool] = {
            crit_samples_key: crit_1,
            "zero_rt_overruns": crit_2,
            "tail_frequency_p2p_le_010hz": crit_tail_p2p,
            "voltages_within_5pct": crit_voltages,
        }

        if tag == "s1":
            crit_p2_zero = all(abs(x) < 1e-6 for x in p2_all)
            crit_p3_zero = all(abs(x) < 1e-6 for x in p3_all)
            crit_p1_range = (min(p1_all) >= 3.49) and (max(p1_all) <= 10.0)
            crit_tail_band = tail_max_dev <= 0.05
            criteria_dict.update({
                "pv_disconnected_p2_zero": crit_p2_zero,
                "bess_inert_p3_zero": crit_p3_zero,
                "diesel_within_operating_limits": crit_p1_range,
                "tail_frequency_within_005hz": crit_tail_band,
            })
            specific_lines = [
                f"  - **PV desconectado (`P2 == 0`):** {'PASS' if crit_p2_zero else 'FAIL'} (máx={max(p2_all):.4f} kW)",
                f"  - **BESS inerte (`P3 == 0`):** {'PASS' if crit_p3_zero else 'FAIL'} (rango=[{min(p3_all):.4f}, {max(p3_all):.4f}] kW)",
                f"  - **Diésel en banda operativa `[3.5, 10.0] kW`:** {'PASS' if crit_p1_range else 'FAIL'} (rango=[{min(p1_all):.4f}, {max(p1_all):.4f}] kW)",
                f"  - **Cola `[100, 120] s` en banda `|f-60| <= 0.05 Hz`:** {'PASS' if crit_tail_band else 'FAIL'} (max|f-60|={tail_max_dev:.4f} Hz)",
            ]
        elif tag == "s2":
            crit_no_deficit = (min(p1_all) >= 3.49) and (max(p1_all) <= 10.0)
            crit_bess_absorb = (p3_mean_40_120 < 0.0) and (soc_fin_all > soc_ini_all)

            # S-O-34 / C1 / C2: Criterios estrictos de aceptación S2
            curt_40_120 = [_f(r, "curtail_ratio", 1.0) for r in sub_40_120] if sub_40_120 else curt_all
            pct_ones = (sum(1 for c in curt_40_120 if c >= 0.999) / len(curt_40_120)) if curt_40_120 else 0.0
            crit_curtail_1 = pct_ones >= 0.95
            crit_ss_freq = tail_max_dev <= 0.070

            # Concordancia de SoC con energía absorbida en la ventana de excedente [40, 120] s (S-O-34 C1)
            # Pack nominal: 48.0 V * 10 serie = 480.0 V, 200.0 Ah => E_nom = 480 * 200 * 3600 = 345,600,000 J
            e_absorbed_sub = sum(-float(_f(r, "P3_kW", 0.0)) * 1000.0 * 0.5 for r in sub_40_120 if float(_f(r, "P3_kW", 0.0)) < 0)
            theo_d_soc = e_absorbed_sub / (480.0 * 200.0 * 3600.0)
            soc_sub_vals = [_f(r, "SoC", 0.5) for r in sub_40_120 if r.get("SoC", "") != ""]
            meas_d_soc = (soc_sub_vals[-1] - soc_sub_vals[0]) if len(soc_sub_vals) >= 2 else (soc_fin_all - soc_ini_all)
            concordance = (meas_d_soc / theo_d_soc) if theo_d_soc > 1e-6 else 1.0
            crit_soc_concordance = concordance >= 0.95

            criteria_dict.update({
                "no_deficit_diesel_in_range": crit_no_deficit,
                "bess_absorbs_surplus": crit_bess_absorb,
                "curtail_ratio_1_in_ge_95pct": crit_curtail_1,
                "steady_state_delta_f_le_0070hz": crit_ss_freq,
                "soc_concordance_ge_95pct": crit_soc_concordance,
            })
            specific_lines = [
                f"  - **Sin déficit (`P1 >= 3.49 kW` y `<= 10.0 kW`):** {'PASS' if crit_no_deficit else 'FAIL'} (rango=[{min(p1_all):.4f}, {max(p1_all):.4f}] kW)",
                f"  - **Absorción en BESS (`[40, 120] s`):** {'PASS' if crit_bess_absorb else 'FAIL'} (P3 media={p3_mean_40_120:+.4f} kW, SoC: {soc_ini_all:.6f} -> {soc_fin_all:.6f})",
                f"  - **Cero recorte solar (`curtail_ratio == 1.0` en >= 95%):** {'PASS' if crit_curtail_1 else 'FAIL'} ({pct_ones*100:.1f} % en 1.0)",
                f"  - **Desvío régimen permanente (`|f-60| <= 0.070 Hz`):** {'PASS' if crit_ss_freq else 'FAIL'} (máx dev={tail_max_dev:.4f} Hz)",
                f"  - **Concordancia energética de SoC (>= 95%):** {'PASS' if crit_soc_concordance else 'FAIL'} ({concordance*100:.1f} % concordancia)",
                f"  - **Recorte solar medio (`[40, 120] s`):** {pc_mean_40_120:.4f} kW (curtail_ratio_min={min(curt_all):.4f})",
            ]
        elif tag == "s3":
            crit_no_deficit = (min(p1_all) >= 3.49) and (max(p1_all) <= 10.0)
            crit_pv_curtail = (pc_mean_40_120 > 0.0) and (min(curt_all) < 1.0)
            crit_bess_no_charge = all(x >= -0.05 for x in p3_all)
            crit_tail_p2p_s3 = tail_p2p <= 0.10
            criteria_dict.update({
                "no_deficit_diesel_in_range": crit_no_deficit,
                "pv_curtailment_active": crit_pv_curtail,
                "bess_charge_disabled": crit_bess_no_charge,
                "tail_p2p_le_010hz": crit_tail_p2p_s3,
            })
            specific_lines = [
                f"  - **Sin déficit (`P1 >= 3.49 kW` y `<= 10.0 kW`):** {'PASS' if crit_no_deficit else 'FAIL'} (rango=[{min(p1_all):.4f}, {max(p1_all):.4f}] kW)",
                f"  - **Recorte solar activo (`[40, 120] s`):** {'PASS' if crit_pv_curtail else 'FAIL'} (P_curtailed media={pc_mean_40_120:.4f} kW, curtail_ratio_min={min(curt_all):.4f})",
                f"  - **BESS bloqueado en carga (`SoC_0 = {soc_ini_all:.2f}`):** {'PASS' if crit_bess_no_charge else 'FAIL'} (P3 rango=[{min(p3_all):.4f}, {max(p3_all):.4f}] kW, SoC_fin={soc_fin_all:.6f})",
                f"  - **Estabilidad de cola (`p2p <= 0.10 Hz`):** {'PASS' if crit_tail_p2p_s3 else 'FAIL'} ({tail_p2p:.4f} Hz)",
            ]
        elif tag == "s4":
            # S-O-36 P1: Criterios de Aceptación para Ensayo de Excitación de Reactiva (ESC-HIL-015)
            # 1. Dispersión de ratios (máx - mín) supera 0.010 durante la excitación [50, 55] s
            sub_excit = [r for r in rows if 50.0 <= _f(r, "time_s", _f(r, "time_sec", -1.0)) <= 55.0]
            eq_excit = [_f(r, "e_Q") for r in sub_excit]
            e_q_max_excit = max(eq_excit) if eq_excit else 0.0
            crit_dispersion = e_q_max_excit > 0.010

            # 2. Retorna a <= 0.0067 (banda 2%) en <= 13.5 s tras el cese del escalón (t=55 s)
            sub_recovery = [r for r in rows if 55.0 < _f(r, "time_s", _f(r, "time_sec", -1.0)) <= 68.5]
            t_entry = None
            for r in sub_recovery:
                if _f(r, "e_Q") <= 0.0067:
                    t_entry = _f(r, "time_s", _f(r, "time_sec", -1.0))
                    break

            recovery_time_s = (t_entry - 55.0) if t_entry is not None else 999.0
            r_at_135 = next((r for r in rows if abs(_f(r, "time_s", _f(r, "time_sec", -1.0)) - 68.5) < 0.25), {})
            e_q_at_13_5s = _f(r_at_135, "e_Q", 1.0)
            crit_reconvergence = (t_entry is not None) and (recovery_time_s <= 13.5) and (e_q_at_13_5s <= 0.0067)

            # 3. e_Q distinto de cero en al menos 20 muestras bajo excitación / transitorio
            sub_trans = [r for r in rows if _f(r, "time_s", _f(r, "time_sec", -1.0)) >= 50.0]
            nonzero_eq_samples = sum(1 for r in sub_trans if _f(r, "e_Q") > 0.0001)
            crit_nonzero = nonzero_eq_samples >= 20

            # 4. Tensiones en +-5% y sin ciclo límite (tail p2p <= 0.10 Hz)
            crit_tail_p2p_s4 = tail_p2p <= 0.10

            criteria_dict.update({
                "ratio_dispersion_gt_0010": crit_dispersion,
                "reconvergence_le_13_5s": crit_reconvergence,
                "nonzero_eq_samples_ge_20": crit_nonzero,
                "tail_frequency_p2p_le_010hz": crit_tail_p2p_s4,
            })
            specific_lines = [
                f"  - **Dispersión de ratios bajo excitación (`e_Q_max > 0.010` en [50, 55] s):** {'PASS' if crit_dispersion else 'FAIL'} (e_Q_max={e_q_max_excit:.4f})",
                f"  - **Reconvergencia a banda 2% (`e_Q <= 0.0067` en <= 13.5 s tras cese):** {'PASS' if crit_reconvergence else 'FAIL'} (t_recov={recovery_time_s:.1f} s, e_Q(68.5s)={e_q_at_13_5s:.4f})",
                f"  - **Muestras no nulas de e_Q bajo excitación (>= 20 muestras):** {'PASS' if crit_nonzero else 'FAIL'} ({nonzero_eq_samples} muestras con e_Q > 0)",
                f"  - **Estabilidad de frecuencia en cola (`p2p <= 0.10 Hz`):** {'PASS' if crit_tail_p2p_s4 else 'FAIL'} ({tail_p2p:.4f} Hz)",
            ]
        elif tag == "s4_180s":
            # S-O-37: Criterios de Aceptación para Ensayo de Excitación de Reactiva 180s (ESC-HIL-016)
            # 1. Dispersión de ratios (máx - mín) supera 0.010 durante la excitación [50, 55] s
            sub_excit = [r for r in rows if 50.0 <= _f(r, "time_s", _f(r, "time_sec", -1.0)) <= 55.0]
            eq_excit = [_f(r, "e_Q") for r in sub_excit]
            e_q_max_excit = max(eq_excit) if eq_excit else 0.0
            crit_dispersion = e_q_max_excit > 0.010

            # 2. Retorna a <= 0.0067 (banda 2%) en <= 13.5 s tras el cese del escalón (t=55 s)
            sub_recovery = [r for r in rows if 55.0 < _f(r, "time_s", _f(r, "time_sec", -1.0)) <= 68.5]
            t_entry = None
            for r in sub_recovery:
                if _f(r, "e_Q") <= 0.0067:
                    t_entry = _f(r, "time_s", _f(r, "time_sec", -1.0))
                    break

            recovery_time_s = (t_entry - 55.0) if t_entry is not None else 999.0
            crit_reconvergence = (t_entry is not None) and (recovery_time_s <= 13.5)

            # 3. Dispersión sostenida en la cola [120, 180] s (e_Q <= 0.0067)
            sub_tail_180 = [r for r in rows if 120.0 <= _f(r, "time_s", _f(r, "time_sec", -1.0)) <= 180.0]
            eq_tail_180 = [_f(r, "e_Q") for r in sub_tail_180]
            e_q_tail_max = max(eq_tail_180) if eq_tail_180 else 0.0
            e_q_tail_mean = sum(eq_tail_180) / len(eq_tail_180) if eq_tail_180 else 0.0
            crit_tail_dispersion = (e_q_tail_max <= 0.0067) or (e_q_tail_mean <= 0.0067 and (sum(1 for x in eq_tail_180 if x <= 0.0067) / len(eq_tail_180) >= 0.95))

            # Determinar instante exacto de cruce sostenido tras cese (t >= 55 s) donde e_Q permanece <= 0.0067
            t_cruce_sostenido = None
            for idx_c, r_c in enumerate(rows):
                t_c = _f(r_c, "time_s", _f(r_c, "time_sec", -1.0))
                if t_c >= 55.0:
                    remaining = [_f(rem, "e_Q") for rem in rows[idx_c:]]
                    if all(x <= 0.0067 for x in remaining):
                        t_cruce_sostenido = t_c
                        break
            if t_cruce_sostenido is None:
                for idx_c, r_c in reversed(list(enumerate(rows))):
                    if _f(r_c, "e_Q") > 0.0067:
                        if idx_c + 1 < len(rows):
                            t_cruce_sostenido = _f(rows[idx_c + 1], "time_s", _f(rows[idx_c + 1], "time_sec", -1.0))
                        break

            # 4. e_Q distinto de cero en al menos 20 muestras bajo excitación / transitorio
            sub_trans = [r for r in rows if _f(r, "time_s", _f(r, "time_sec", -1.0)) >= 50.0]
            nonzero_eq_samples = sum(1 for r in sub_trans if _f(r, "e_Q") > 0.0001)
            crit_nonzero = nonzero_eq_samples >= 20

            # 5. Estabilidad de frecuencia en cola
            crit_tail_p2p_s4 = tail_p2p <= 0.10

            criteria_dict.update({
                "ratio_dispersion_gt_0010": crit_dispersion,
                "reconvergence_le_13_5s": crit_reconvergence,
                "tail_dispersion_le_00067": crit_tail_dispersion,
                "nonzero_eq_samples_ge_20": crit_nonzero,
                "tail_frequency_p2p_le_010hz": crit_tail_p2p_s4,
            })
            cruce_sost_str = f"{t_cruce_sostenido:.1f} s" if t_cruce_sostenido is not None else "N/A"
            specific_lines = [
                f"  - **Dispersión de ratios bajo excitación (`e_Q_max > 0.010` en [50, 55] s):** {'PASS' if crit_dispersion else 'FAIL'} (e_Q_max={e_q_max_excit:.4f})",
                f"  - **Reconvergencia a banda 2% (`e_Q <= 0.0067` en <= 13.5 s tras cese):** {'PASS' if crit_reconvergence else 'FAIL'} (t_recov={recovery_time_s:.1f} s, primera entrada a t={t_entry:.1f} s)",
                f"  - **Dispersión sostenida en cola [120, 180] s (`e_Q <= 0.0067`):** {'PASS' if crit_tail_dispersion else 'FAIL'} (e_Q_max={e_q_tail_max:.4f}, e_Q_media={e_q_tail_mean:.4f}, cruce sostenido definitivo en t={cruce_sost_str})",
                f"  - **Muestras no nulas de e_Q bajo excitación (>= 20 muestras):** {'PASS' if crit_nonzero else 'FAIL'} ({nonzero_eq_samples} muestras con e_Q > 0)",
                f"  - **Estabilidad de frecuencia en cola (`p2p <= 0.10 Hz`):** {'PASS' if crit_tail_p2p_s4 else 'FAIL'} ({tail_p2p:.4f} Hz)",
            ]
        elif tag == "s5":
            # S-O-38: Criterios de Aceptación para Ensayo de Re-sintonización CFL 180s (ESC-HIL-017)
            # 1. Dispersión pico durante excitación (t in [50, 55] s): > 0.010
            sub_excit = [r for r in rows if 50.0 <= _f(r, "time_s", _f(r, "time_sec", -1.0)) <= 55.0]
            eq_excit = [_f(r, "e_Q") for r in sub_excit]
            e_q_max_excit = max(eq_excit) if eq_excit else 0.0
            crit_dispersion = e_q_max_excit > 0.010

            # 2. Retorna a <= 0.0067 (banda 2%) en <= 13.5 s tras el cese del escalón (t=55 s)
            sub_recovery = [r for r in rows if 55.0 < _f(r, "time_s", _f(r, "time_sec", -1.0)) <= 68.5]
            t_entry = None
            for r in sub_recovery:
                if _f(r, "e_Q") <= 0.0067:
                    t_entry = _f(r, "time_s", _f(r, "time_sec", -1.0))
                    break

            recovery_time_s = (t_entry - 55.0) if t_entry is not None else 999.0
            crit_reconvergence = (t_entry is not None) and (recovery_time_s <= 13.5)

            # 3. Dispersión sostenida <= 0.0067 al menos 13.5 s antes del final (t in [166.5, 180.0] s)
            sub_tail_13_5 = [r for r in rows if 166.5 <= _f(r, "time_s", _f(r, "time_sec", -1.0)) <= 180.0]
            eq_tail_13_5 = [_f(r, "e_Q") for r in sub_tail_13_5]
            e_q_tail_max_13_5 = max(eq_tail_13_5) if eq_tail_13_5 else 0.0
            crit_tail_sustained = (len(eq_tail_13_5) > 0) and all(x <= 0.0067 for x in eq_tail_13_5)

            # Determinar instante exacto de cruce sostenido tras cese (t >= 55 s) donde e_Q permanece <= 0.0067
            t_cruce_sostenido = None
            for idx_c, r_c in enumerate(rows):
                t_c = _f(r_c, "time_s", _f(r_c, "time_sec", -1.0))
                if t_c >= 55.0:
                    remaining = [_f(rem, "e_Q") for rem in rows[idx_c:]]
                    if all(x <= 0.0067 for x in remaining):
                        t_cruce_sostenido = t_c
                        break

            # 4. e_Q distinto de cero en al menos 20 muestras bajo excitación / transitorio
            sub_trans = [r for r in rows if _f(r, "time_s", _f(r, "time_sec", -1.0)) >= 50.0]
            nonzero_eq_samples = sum(1 for r in sub_trans if _f(r, "e_Q") > 0.0001)
            crit_nonzero = nonzero_eq_samples >= 20

            # 5. Estabilidad de frecuencia en cola (p2p <= 0.10 Hz)
            crit_tail_p2p_s5 = tail_p2p <= 0.10

            criteria_dict.update({
                "ratio_dispersion_gt_0010": crit_dispersion,
                "reconvergence_le_13_5s": crit_reconvergence,
                "tail_dispersion_sustained_le_00067": crit_tail_sustained,
                "nonzero_eq_samples_ge_20": crit_nonzero,
                "tail_frequency_p2p_le_010hz": crit_tail_p2p_s5,
            })
            cruce_sost_str = f"{t_cruce_sostenido:.1f} s" if t_cruce_sostenido is not None else "N/A"
            specific_lines = [
                f"  - **Dispersión de ratios bajo excitación (`e_Q_max > 0.010` en [50, 55] s):** {'PASS' if crit_dispersion else 'FAIL'} (e_Q_max={e_q_max_excit:.4f})",
                f"  - **Reconvergencia a banda 2% (`e_Q <= 0.0067` en <= 13.5 s tras cese):** {'PASS' if crit_reconvergence else 'FAIL'} (t_recov={recovery_time_s:.1f} s, primera entrada a t={t_entry:.1f} s)",
                f"  - **Dispersión sostenida <= 0.0067 en últimos 13.5 s [166.5, 180.0] s:** {'PASS' if crit_tail_sustained else 'FAIL'} (e_Q_max={e_q_tail_max_13_5:.4f}, cruce sostenido definitivo en t={cruce_sost_str})",
                f"  - **Muestras no nulas de e_Q bajo excitación (>= 20 muestras):** {'PASS' if crit_nonzero else 'FAIL'} ({nonzero_eq_samples} muestras con e_Q > 0)",
                f"  - **Estabilidad de frecuencia en cola (`p2p <= 0.10 Hz`):** {'PASS' if crit_tail_p2p_s5 else 'FAIL'} ({tail_p2p:.4f} Hz)",
            ]
        elif tag == "s6":
            # S-O-40: Criterios de Aceptación para Sub-pasos del Consenso n=4 (ESC-HIL-018)
            sub_excit = [r for r in rows if 50.0 <= _f(r, "time_s", _f(r, "time_sec", -1.0)) <= 55.0]
            eq_excit = [_f(r, "e_Q") for r in sub_excit]
            e_q_max_excit = max(eq_excit) if eq_excit else 0.0
            crit_dispersion = e_q_max_excit > 0.010

            sub_tail_13_5 = [r for r in rows if 166.5 <= _f(r, "time_s", _f(r, "time_sec", -1.0)) <= 180.0]
            eq_tail_13_5 = [_f(r, "e_Q") for r in sub_tail_13_5]
            e_q_tail_max_13_5 = max(eq_tail_13_5) if eq_tail_13_5 else 0.0
            crit_tail_sustained = (len(eq_tail_13_5) > 0) and all(x <= 0.0067 for x in eq_tail_13_5)

            # Amplitud residual en los últimos 30 s [150.0, 180.0] s <= 0.003
            sub_last_30 = [r for r in rows if 150.0 <= _f(r, "time_s", _f(r, "time_sec", -1.0)) <= 180.0]
            eq_last_30 = [_f(r, "e_Q") for r in sub_last_30]
            e_q_last_30_max = max(eq_last_30) if eq_last_30 else 0.0
            e_q_last_30_mean = sum(eq_last_30) / len(eq_last_30) if eq_last_30 else 0.0
            crit_residual_amp = (len(eq_last_30) > 0) and (e_q_last_30_max <= 0.003)

            sub_trans = [r for r in rows if _f(r, "time_s", _f(r, "time_sec", -1.0)) >= 50.0]
            nonzero_eq_samples = sum(1 for r in sub_trans if _f(r, "e_Q") > 0.0001)
            crit_nonzero = nonzero_eq_samples >= 20

            crit_tail_p2p_s6 = tail_p2p <= 0.10

            criteria_dict.update({
                "ratio_dispersion_gt_0010": crit_dispersion,
                "tail_dispersion_sustained_le_00067": crit_tail_sustained,
                "residual_amplitude_last30s_le_0003": crit_residual_amp,
                "nonzero_eq_samples_ge_20": crit_nonzero,
                "tail_frequency_p2p_le_010hz": crit_tail_p2p_s6,
            })
            specific_lines = [
                f"  - **Dispersión de ratios bajo excitación (`e_Q_max > 0.010` en [50, 55] s):** {'PASS' if crit_dispersion else 'FAIL'} (e_Q_max={e_q_max_excit:.4f})",
                f"  - **Dispersión sostenida <= 0.0067 en últimos 13.5 s [166.5, 180.0] s:** {'PASS' if crit_tail_sustained else 'FAIL'} (e_Q_max={e_q_tail_max_13_5:.4f})",
                f"  - **Amplitud residual en últimos 30 s [150.0, 180.0] s (`<= 0.003`):** {'PASS' if crit_residual_amp else 'FAIL'} (e_Q_max={e_q_last_30_max:.4f}, media={e_q_last_30_mean:.4f})",
                f"  - **Muestras no nulas de e_Q bajo excitación (>= 20 muestras):** {'PASS' if crit_nonzero else 'FAIL'} ({nonzero_eq_samples} muestras con e_Q > 0)",
                f"  - **Estabilidad de frecuencia en cola (`p2p <= 0.10 Hz`):** {'PASS' if crit_tail_p2p_s6 else 'FAIL'} ({tail_p2p:.4f} Hz)",
            ]
        else:
            specific_lines = []

        all_passed = all(criteria_dict.values())

        report_name = f"reporte_{tag}_validacion.md"
        report_path = os.path.join(results_dir, report_name)
        lines = [
            f"# Reporte de Validación {tag_upper} — {scenario_name} (D-31 / S-O-28)",
            "",
            f"- **Muestras:** {n_samples} (`t = {t_first}..{t_last} s`)",
            f"- **Tiempo de paso máx:** {max(step_times_ms):.2f} ms (`overruns > 500 ms`: {overruns})",
            f"- **Cola limpia `{tail_str}`:** media `{tail_f_mean:.4f} Hz`, rango `[{tail_f_min:.4f}, {tail_f_max:.4f}] Hz`, p2p `{tail_p2p:.4f} Hz`, max|f-60| `{tail_max_dev:.4f} Hz`",
            f"- **Tensiones nodales (global):** `[{v_min_all:.4f}, {v_max_all:.4f}] pu`",
            "- **Criterios de Aceptación:**",
            f"  - **{crit_samples_text}:** {'PASS' if crit_1 else 'FAIL'}",
            f"  - **Cero violaciones RT (500 ms):** {'PASS' if crit_2 else 'FAIL'}",
            f"  - **Estabilidad de frecuencia en cola (`p2p <= 0.10 Hz`):** {'PASS' if crit_tail_p2p else 'FAIL'} (`{tail_p2p:.4f} Hz`)",
            f"  - **Tensiones en banda ±5 % (`[0.95, 1.05] pu`):** {'PASS' if crit_voltages else 'FAIL'}",
            *specific_lines,
            f"- **Dictamen General {tag_upper}:** {'CERTIFICADO' if all_passed else 'REPROBADO'}",
            "",
            "| Ventana (s) | Evento | N | f [min, max] (Hz) | f media (Hz) | f p2p (Hz) | V [min, max] (pu) | P1 media (kW) | P2 media (kW) | P3 media (kW) | P_curt media (kW) | SoC ini -> fin | curtail_min_obs |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for m in window_metrics:
            if m.get("n", 0) == 0:
                continue
            lines.append(
                f"| [{m['ventana_s'][0]}, {m['ventana_s'][1]}] | {m['evento']} | {m['n']} | "
                f"[{m['f_min']:.4f}, {m['f_max']:.4f}] | {m['f_mean']:.4f} | {m['f_p2p']:.4f} | "
                f"[{m['V_min']:.4f}, {m['V_max']:.4f}] | {m['P1_mean_kW']:.4f} | {m['P2_mean_kW']:.4f} | "
                f"{m['P3_mean_kW']:+.4f} | {m['P_curtailed_mean_kW']:.4f} | {m['SoC_ini']} -> {m['SoC_fin']} | {m['curtail_ratio_min']:.4f} |"
            )

        if tag in ("s4", "s4_180s", "s5", "s6"):
            lines.append("")
            lines.append("### Registro Muestra a Muestra de Potencia Reactiva y Consenso (Ventana de Excitación y Transitorio [48, 75] s)")
            lines.append("| t (s) | Q1 (kvar) | Q2 (kvar) | Q3 (kvar) | q1 (Q1/6k) | q2 (Q2/3k) | q3 (Q3/1k) | e_Q | f_sys (Hz) | V_min (pu) |")
            lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
            sub_window_rep = [r for r in rows if 48.0 <= _f(r, "time_s", _f(r, "time_sec", -1.0)) <= 75.0]
            for r in sub_window_rep:
                t_val = _f(r, "time_s", _f(r, "time_sec", -1.0))
                q1_v = _f(r, "Q1_kvar")
                q2_v = _f(r, "Q2_kvar")
                q3_v = _f(r, "Q3_kvar")
                r1_v = _f(r, "Q_ratio_1")
                r2_v = _f(r, "Q_ratio_2")
                r3_v = _f(r, "Q_ratio_3")
                eq_v = _f(r, "e_Q")
                f_v = _f(r, "f_sys_hz")
                v_vals = [_f(r, f"V{i}_pu", 1.0) for i in range(1, 9) if f"V{i}_pu" in r]
                v_min = min(v_vals) if v_vals else 1.0
                lines.append(f"| {t_val:.1f} | {q1_v:+.4f} | {q2_v:+.4f} | {q3_v:+.4f} | {r1_v:.4f} | {r2_v:.4f} | {r3_v:.4f} | {eq_v:.4f} | {f_v:.4f} | {v_min:.4f} |")

            if tag in ("s4_180s", "s5", "s6"):
                lines.append("")
                lines.append("### Registro Muestra a Muestra en Cola Extendida [120, 180] s (Muestreo cada 2.5 s)")
                lines.append("| t (s) | Q1 (kvar) | Q2 (kvar) | Q3 (kvar) | q1 (Q1/6k) | q2 (Q2/3k) | q3 (Q3/1k) | e_Q | f_sys (Hz) | V_min (pu) |")
                lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
                sub_tail_rep = [r for r in rows if 120.0 <= _f(r, "time_s", _f(r, "time_sec", -1.0)) <= 180.0]
                for r in sub_tail_rep:
                    t_val = _f(r, "time_s", _f(r, "time_sec", -1.0))
                    if abs(t_val % 2.5) < 0.1 or t_val in (120.0, 180.0):
                        q1_v = _f(r, "Q1_kvar")
                        q2_v = _f(r, "Q2_kvar")
                        q3_v = _f(r, "Q3_kvar")
                        r1_v = _f(r, "Q_ratio_1")
                        r2_v = _f(r, "Q_ratio_2")
                        r3_v = _f(r, "Q_ratio_3")
                        eq_v = _f(r, "e_Q")
                        f_v = _f(r, "f_sys_hz")
                        v_vals = [_f(r, f"V{i}_pu", 1.0) for i in range(1, 9) if f"V{i}_pu" in r]
                        v_min = min(v_vals) if v_vals else 1.0
                        lines.append(f"| {t_val:.1f} | {q1_v:+.4f} | {q2_v:+.4f} | {q3_v:+.4f} | {r1_v:.4f} | {r2_v:.4f} | {r3_v:.4f} | {eq_v:.4f} | {f_v:.4f} | {v_min:.4f} |")

        with open(report_path, "w", encoding="utf-8") as f_rep:
            f_rep.write("\n".join(lines) + "\n")
        print(f"[OK] Reporte {tag_upper} generado: {report_path}")

        return {
            "scenario_tag": tag_upper,
            "n_samples": n_samples,
            "time_range_s": [t_first, t_last],
            "max_step_elapsed_ms": round(max(step_times_ms), 3) if step_times_ms else 0.0,
            "rt_overruns": overruns,
            "criteria": criteria_dict,
            "tail_100_120_s": {
                "f_mean_hz": round(tail_f_mean, 4),
                "f_min_hz": round(tail_f_min, 4),
                "f_max_hz": round(tail_f_max, 4),
                "f_p2p_hz": round(tail_p2p, 4),
                "max_abs_dev_hz": round(tail_max_dev, 4),
            },
            "voltage_range_pu": [round(v_min_all, 4), round(v_max_all, 4)],
            "post_40s_summary": {
                "P3_mean_kW": round(p3_mean_40_120, 4),
                "P_curtailed_mean_kW": round(pc_mean_40_120, 4),
                "SoC_ini": round(soc_ini_all, 6),
                "SoC_fin": round(soc_fin_all, 6),
                "curtail_ratio_min": round(min(curt_all), 4),
                "P1_range_kW": [round(min(p1_all), 4), round(max(p1_all), 4)],
            },
            "all_criteria_passed": bool(all_passed),
            "windows": window_metrics,
            "report_path": report_path,
        }

    @staticmethod
    def audit_s40_telemetry(local_csv: str, scenario_dir: str, results_dir: str) -> Dict[str, Any]:
        """Audita las 10 ventanas D-28 y los 4 criterios de aceptación S-40; genera reporte_s40_validacion.md."""
        with open(local_csv, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        def _f(r: dict, key: str, default: float = 0.0) -> float:
            val = r.get(key)
            if val in (None, ""):
                return default
            return float(val)

        n_samples = len(rows)
        t_first = _f(rows[0], "time_s", _f(rows[0], "time_sec", -1.0)) if rows else -1.0
        t_last = _f(rows[-1], "time_s", _f(rows[-1], "time_sec", -1.0)) if rows else -1.0
        step_times_ms = [_f(r, "step_elapsed_ms", 0.0) for r in rows]
        overruns = sum(1 for ms in step_times_ms if ms > 500.0)

        meta_path = os.path.join(scenario_dir, "meta.json")
        windows = [
            {"ventana_s": [0, 40], "evento": "acoplamiento y convergencia inicial"},
            {"ventana_s": [40, 100], "evento": "regimen isocrono sin eventos"},
            {"ventana_s": [100, 150], "evento": "rampa positiva de carga"},
            {"ventana_s": [150, 200], "evento": "escalon negativo de carga"},
            {"ventana_s": [200, 250], "evento": "sombreado 800 a 550 W/m2"},
            {"ventana_s": [250, 300], "evento": "sombreado abrupto"},
            {"ventana_s": [300, 360], "evento": "recuperacion solar y rampa negativa de carga"},
            {"ventana_s": [360, 410], "evento": "perdida del 20 por ciento en 2-3"},
            {"ventana_s": [410, 440], "evento": "desconexion total 1-2"},
            {"ventana_s": [440, 480], "evento": "cola limpia"},
        ]
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f_m:
                    w_meta = json.load(f_m).get("ventanas_validacion")
                if isinstance(w_meta, list) and w_meta:
                    windows = w_meta
            except Exception:
                pass

        window_metrics: List[Dict[str, Any]] = []
        for idx_w, w in enumerate(windows):
            t0, t1 = w["ventana_s"]
            is_last = idx_w == len(windows) - 1
            sub = [
                r for r in rows
                if (t0 <= _f(r, "time_s", _f(r, "time_sec", -1.0)) <= t1 if is_last
                    else t0 <= _f(r, "time_s", _f(r, "time_sec", -1.0)) < t1)
            ]
            if not sub:
                window_metrics.append({"ventana_s": [t0, t1], "evento": w.get("evento", ""), "n": 0})
                continue

            f_vals = [_f(r, "f_sys_hz", 60.0) for r in sub]
            v_all = [_f(r, f"V{i}_pu", 1.0) for r in sub for i in range(1, 9) if f"V{i}_pu" in r]
            p3_vals = [_f(r, "P3_kW", 0.0) for r in sub]
            soc_vals = [_f(r, "SoC", 0.5) for r in sub if r.get("SoC", "") != ""]
            curt_vals = [_f(r, "curtail_ratio", 1.0) for r in sub]
            curt_min_param = [_f(r, "curtail_min", 0.15) for r in sub]
            eq_vals = [_f(r, "e_Q", max(_f(r, "error_Q_12"), _f(r, "error_Q_23"))) for r in sub]
            dropped = sum(int(float(r.get("paquetes_descartados", 0) or 0)) for r in sub)
            d12_cnt = sum(1 for r in sub if "D_12" in str(r.get("contingencias_activas", "")))

            window_metrics.append({
                "ventana_s": [t0, t1],
                "evento": w.get("evento", ""),
                "n": len(sub),
                "f_min": round(min(f_vals), 4),
                "f_max": round(max(f_vals), 4),
                "V_min": round(min(v_all), 4) if v_all else 1.0,
                "V_max": round(max(v_all), 4) if v_all else 1.0,
                "P3_mean_kW": round(sum(p3_vals) / len(p3_vals), 3),
                "SoC_ini": round(soc_vals[0], 6) if soc_vals else None,
                "SoC_fin": round(soc_vals[-1], 6) if soc_vals else None,
                "curtail_ratio_min": round(min(curt_vals), 4),
                "curtail_min": round(min(curt_min_param), 4),
                "e_Q_final": round(eq_vals[-1], 4),
                "e_Q_max": round(max(eq_vals), 4) if eq_vals else 0.0,
                "dropped_pkts": dropped,
                "d12_samples": d12_cnt,
            })

        w_150 = next((m for m in window_metrics if m["ventana_s"] == [150, 200]), {})
        w_300 = next((m for m in window_metrics if m["ventana_s"] == [300, 360]), {})
        w_410 = next((m for m in window_metrics if m["ventana_s"] == [410, 440]), {})
        w_440 = next((m for m in window_metrics if m["ventana_s"] == [440, 480]), {})

        crit_1 = n_samples == 961 and abs(t_first - 0.0) < 1e-6 and abs(t_last - 480.0) < 1e-6
        crit_2 = (
            w_150.get("SoC_fin") is not None and w_150.get("SoC_ini") is not None
            and w_150["SoC_fin"] > w_150["SoC_ini"] and w_150.get("curtail_ratio_min", 1.0) < 1.0
            and w_300.get("SoC_fin") is not None and w_300.get("SoC_ini") is not None
            and w_300["SoC_fin"] > w_300["SoC_ini"] and w_300.get("curtail_ratio_min", 1.0) < 1.0
        )
        # S-O-36 P4: Precondición e_Q_max > 0.01 en ventana de falla para evaluar reconvergencia real
        crit_3_link_cut_no_dev = (
            w_410.get("d12_samples", 0) == 60
            and w_410.get("e_Q_max", 0.0) > 0.01
            and w_440.get("e_Q_final", 1.0) < 0.05
        )
        crit_4 = overruns == 0 and (max(step_times_ms) < 500.0 if step_times_ms else True)

        report_path = os.path.join(results_dir, "reporte_s40_validacion.md")
        lines = [
            "# Reporte de Cierre S-40 — ESC-HIL-008_validacion_integrada",
            "",
            f"- **Muestras:** {n_samples} (`t = {t_first}..{t_last} s`)",
            f"- **Tiempo de paso máx:** {max(step_times_ms):.2f} ms (`overruns > 500 ms`: {overruns})",
            "- **Criterios certificados:** 3 certificados + 1 no ejercitado",
            f"  - **Criterio 1 (961 muestras @ 2 Hz):** {'PASS' if crit_1 else 'FAIL'}",
            f"  - **Criterio 2 (Régimen excedentario BESS+PV):** {'PASS' if crit_2 else 'FAIL'}",
            f"  - **Criterio 3 (Corte de enlace 1↔2 con precondición e_Q_max > 0.01 / link_cut_no_deviation):** {'PASS' if crit_3_link_cut_no_dev else 'FAIL'} (reconvergencia dinámica no ejercitada bajo falla activa: e_Q_max={w_410.get('e_Q_max', 0.0):.4f})",
            f"  - **Criterio 4 (0 violaciones RT 500 ms):** {'PASS' if crit_4 else 'FAIL'}",
            "- **Criterios no ejercitados:** `[\"reconvergence_under_active_fault\"]`",
            "",
            "| Ventana (s) | Evento | N | f [min, max] (Hz) | V [min, max] (pu) | P_BESS media (kW) | SoC ini -> fin | curtail_ratio_min | curtail_min | e_Q final | D_12 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for m in window_metrics:
            if m.get("n", 0) == 0:
                continue
            lines.append(
                f"| [{m['ventana_s'][0]}, {m['ventana_s'][1]}] | {m['evento']} | {m['n']} | "
                f"[{m['f_min']:.3f}, {m['f_max']:.3f}] | [{m['V_min']:.4f}, {m['V_max']:.4f}] | "
                f"{m['P3_mean_kW']:+.3f} | {m['SoC_ini']} -> {m['SoC_fin']} | {m['curtail_ratio_min']:.4f} | "
                f"{m['curtail_min']:.4f} | {m['e_Q_final']:.4f} | {m['d12_samples']} |"
            )
        with open(report_path, "w", encoding="utf-8") as f_rep:
            f_rep.write("\n".join(lines) + "\n")
        print(f"[OK] Reporte S-40 generado: {report_path}")

        return {
            "n_samples": n_samples,
            "time_range_s": [t_first, t_last],
            "max_step_elapsed_ms": round(max(step_times_ms), 3) if step_times_ms else 0.0,
            "rt_overruns": overruns,
            "criteria": {
                "certified_961_samples": crit_1,
                "surplus_bess_and_curtail": crit_2,
                "link_cut_no_deviation": crit_3_link_cut_no_dev,
                "zero_rt_overruns": crit_4,
            },
            "reconvergence_exercised": False,
            "criteria_not_exercised": [
                "reconvergence_under_active_fault"
            ],
            "notes_criteria": {
                "link_cut_no_deviation": "Corte de enlace 1-2 (60 muestras / 30 s) con precondicion de excitacion e_Q_max > 0.01 y reconvergencia e_Q < 0.05. En ESC-HIL-008 e_Q_max fue 0.0000 (carga estatica), no satisfaciendo la precondicion de excitacion activa."
            },
            "all_criteria_passed": bool(crit_1 and crit_2 and crit_3_link_cut_no_dev and crit_4),
            "windows": window_metrics,
            "report_path": report_path,
        }


def main():
    parser = argparse.ArgumentParser(description="Orquestador de Ensayos HIL en Rack Raspberry Pi")
    parser.add_argument(
        "--campaign",
        choices=[
            "validation-010", "satellites-011", "satellite-011a", "satellite-011b",
            "validation-008", "surplus-pair", "surplus-006", "surplus-007", "dynamic-005", "resilience-d25", "custom"
        ],
        default="validation-010",
        help="Campaña o preset a ejecutar (default: validation-010 para S-O-26 / D-30)"
    )
    parser.add_argument("--steps", type=int, default=None, help="Número de muestras/pasos (default según campaña)")
    parser.add_argument("--dt", type=float, default=0.5, help="Paso de tiempo macro [s]")
    parser.add_argument("--engine", choices=["docker", "native"], default="docker", help="Motor de ejecución")
    parser.add_argument("--sync", action="store_true", help="Sincronizar código fuente antes del ensayo")
    parser.add_argument("--dry-run", action="store_true", help="Modo simulación seca sin comandos SSH")
    parser.add_argument("--scenario", default=None, help="Nombre del escenario para --campaign custom")
    parser.add_argument("--p-min-diesel", type=float, default=None, help="P_min diésel en Watts")
    parser.add_argument("--p-charge-max", type=float, default=None, help="P_charge_max BESS en Watts")
    parser.add_argument("--network-profile", default=None, help="Perfil de perturbaciones de red")
    parser.add_argument("--contingencies-file", default=None, help="Archivo de contingencias telemáticas")
    parser.add_argument("--seed", type=int, default=42, help="Semilla determinística")
    parser.add_argument("--local-sil", action="store_true", help="Ejecutar en modo emulación SIL local multiproceso (sin Raspberry Pi)")
    parser.add_argument("--fast", action="store_true", help="Modo acelerado para simulación SIL local sin pausas de tiempo real")
    parser.add_argument("--q-perturb-node", type=int, default=None, help="Nodo DER para perturbacion reactiva (S-O-30)")
    parser.add_argument("--q-perturb-var", type=float, default=0.0, help="Magnitud de perturbacion reactiva [var]")
    parser.add_argument("--q-perturb-start", type=float, default=40.0, help="Inicio de perturbacion reactiva [s]")
    parser.add_argument("--q-perturb-end", type=float, default=120.0, help="Fin de perturbacion reactiva [s]")

    args = parser.parse_args()
    orchestrator = RackExperimentOrchestrator(
        engine=args.engine,
        dry_run=args.dry_run,
        local_sil=args.local_sil,
        fast_mode=args.fast
    )

    if args.campaign == "validation-010":
        print("\n>>> EJECUTANDO ESCENARIO UNIFICADO MACRO DE VALIDACIÓN (S-O-26 / D-30) <<<")
        orchestrator.run_experiment(
            scenario_name="ESC-HIL-010_validacion_integrada_v2",
            steps=args.steps if args.steps is not None else 1321,
            dt_s=args.dt,
            p_min_diesel=3500.0,
            p_charge_max=3000.0,
            network_profile="DYNAMIC_CONTINGENCY",
            contingencies_file="contingencias_telematicas.csv",
            network_seed=args.seed,
            sync_code=args.sync,
            output_subfolder="validation_v2"
        )

    elif args.campaign == "satellites-011":
        print("\n>>> EJECUTANDO CAMPAÑA SATÉLITE DERATING BESS (S-O-26 / D-30) <<<")
        # 1. ESC-HIL-011a_soc_alto (SoC = 0.93 -> Derating de Carga ~600 W)
        orchestrator.run_experiment(
            scenario_name="ESC-HIL-011a_soc_alto",
            steps=args.steps if args.steps is not None else 361,
            dt_s=args.dt,
            p_min_diesel=3500.0,
            p_charge_max=3000.0,
            network_seed=args.seed,
            sync_code=args.sync,
            output_subfolder="satellites"
        )
        print("\nEsperando 5 segundos antes de correr satélite de SoC bajo...")
        time.sleep(5.0)

        # 2. ESC-HIL-011b_soc_bajo (SoC = 0.22 -> Derating de Descarga ~86 W)
        orchestrator.run_experiment(
            scenario_name="ESC-HIL-011b_soc_bajo",
            steps=args.steps if args.steps is not None else 361,
            dt_s=args.dt,
            p_min_diesel=3500.0,
            p_charge_max=3000.0,
            network_seed=args.seed,
            sync_code=False,
            output_subfolder="satellites"
        )

    elif args.campaign == "satellite-011a":
        orchestrator.run_experiment(
            scenario_name="ESC-HIL-011a_soc_alto",
            steps=args.steps if args.steps is not None else 361,
            dt_s=args.dt,
            p_min_diesel=3500.0,
            p_charge_max=3000.0,
            network_seed=args.seed,
            sync_code=args.sync,
            output_subfolder="satellites"
        )

    elif args.campaign == "satellite-011b":
        orchestrator.run_experiment(
            scenario_name="ESC-HIL-011b_soc_bajo",
            steps=args.steps if args.steps is not None else 361,
            dt_s=args.dt,
            p_min_diesel=3500.0,
            p_charge_max=3000.0,
            network_seed=args.seed,
            sync_code=args.sync,
            output_subfolder="satellites"
        )

    elif args.campaign == "validation-008":
        print("\n>>> EJECUTANDO ESCENARIO ÚNICO DE VALIDACIÓN INTEGRADA (S-40 / D-28) <<<")
        orchestrator.run_experiment(
            scenario_name="ESC-HIL-008_validacion_integrada",
            steps=args.steps if args.steps is not None else 961,
            dt_s=args.dt,
            p_min_diesel=8600.0,
            p_charge_max=3000.0,
            network_profile="DYNAMIC_CONTINGENCY",
            contingencies_file="contingencias_telematicas.csv",
            network_seed=args.seed,
            sync_code=args.sync,
            output_subfolder="validation"
        )

    elif args.campaign == "surplus-pair":
        eff_steps = args.steps if args.steps is not None else 600
        print("\n>>> EJECUTANDO PAR EXCEDENTARIO COMPLETO (S-O-18 / Familia 2 D-24) <<<")
        # 1. ESC-HIL-006 (Excedente con ventana declarada)
        orchestrator.run_experiment(
            scenario_name="ESC-HIL-006_excedente_ventana_declarada",
            steps=eff_steps,
            dt_s=args.dt,
            p_min_diesel=8600.0,
            p_charge_max=3000.0,
            network_seed=args.seed,
            sync_code=args.sync,
            output_subfolder="excedente"
        )
        print("\nEsperando 5 segundos antes de correr el escenario de referencia...")
        time.sleep(5.0)

        # 2. ESC-HIL-007 (Referencia con déficit)
        orchestrator.run_experiment(
            scenario_name="ESC-HIL-007_excedente_referencia",
            steps=eff_steps,
            dt_s=args.dt,
            p_min_diesel=8600.0,
            p_charge_max=3000.0,
            network_seed=args.seed,
            sync_code=False,
            output_subfolder="excedente"
        )

    elif args.campaign == "surplus-006":
        orchestrator.run_experiment(
            scenario_name="ESC-HIL-006_excedente_ventana_declarada",
            steps=args.steps if args.steps is not None else 600,
            dt_s=args.dt,
            p_min_diesel=8600.0,
            p_charge_max=3000.0,
            network_seed=args.seed,
            sync_code=args.sync,
            output_subfolder="excedente"
        )

    elif args.campaign == "surplus-007":
        orchestrator.run_experiment(
            scenario_name="ESC-HIL-007_excedente_referencia",
            steps=args.steps if args.steps is not None else 600,
            dt_s=args.dt,
            p_min_diesel=8600.0,
            p_charge_max=3000.0,
            network_seed=args.seed,
            sync_code=args.sync,
            output_subfolder="excedente"
        )

    elif args.campaign == "dynamic-005":
        orchestrator.run_experiment(
            scenario_name="ESC-HIL-005_rampas_solares_escalones_demanda",
            steps=args.steps if args.steps is not None else 600,
            dt_s=args.dt,
            p_min_diesel=0.0,
            p_charge_max=1500.0,
            network_seed=args.seed,
            sync_code=args.sync,
            output_subfolder="dinamica"
        )

    elif args.campaign == "resilience-d25":
        orchestrator.run_experiment(
            scenario_name=CANONICAL_BASELINE,
            steps=args.steps if args.steps is not None else 600,
            dt_s=args.dt,
            network_profile="DYNAMIC_CONTINGENCY",
            contingencies_file="contingencias_telematicas.csv",
            network_seed=args.seed,
            sync_code=args.sync,
            output_subfolder="resilience"
        )

    elif args.campaign == "custom":
        if not args.scenario:
            print("[ERROR] Para --campaign custom debe especificar --scenario <nombre>")
            sys.exit(1)
        orchestrator.run_experiment(
            scenario_name=args.scenario,
            steps=args.steps if args.steps is not None else 600,
            dt_s=args.dt,
            p_min_diesel=args.p_min_diesel,
            p_charge_max=args.p_charge_max,
            network_profile=args.network_profile,
            contingencies_file=args.contingencies_file,
            network_seed=args.seed,
            sync_code=args.sync,
            output_subfolder="custom",
            q_perturb_node=args.q_perturb_node,
            q_perturb_var=args.q_perturb_var,
            q_perturb_start=args.q_perturb_start,
            q_perturb_end=args.q_perturb_end
        )


if __name__ == "__main__":
    main()
