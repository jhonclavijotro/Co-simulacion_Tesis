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
import time
import json
import hashlib
import argparse
from datetime import datetime
from typing import Dict, Any, Optional

# Cargar dependencias locales
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Scripts.cluster_deployer import ClusterDeployer, get_local_ip
from Central_PC.power_flow_clock_server import PowerFlowClockServer


CANONICAL_BASELINE = "ESC-HIL-003_consolidado_rev5"
FORMS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Forms", "escenarios_generados"))
ACTIVO_FILE = os.path.join(FORMS_DIR, "ACTIVO.txt")


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
        dry_run: bool = False
    ):
        self.list_file = list_file
        self.engine = engine
        self.dry_run = dry_run
        self.deployer = ClusterDeployer(list_path=list_file)
        self.local_ip = get_local_ip()

    def set_active_scenario(self, scenario_name: str, sync_remote: bool = True):
        """Establece el escenario activo local y remotamente en las Raspberry Pis."""
        scenario_path = os.path.join(FORMS_DIR, scenario_name)
        if not os.path.exists(scenario_path):
            raise FileNotFoundError(f"El escenario '{scenario_name}' no existe en {FORMS_DIR}")

        print(f"[ESCENARIO] Estableciendo escenario activo -> '{scenario_name}'")
        with open(ACTIVO_FILE, "w", encoding="utf-8") as f:
            f.write(scenario_name.strip())

        if sync_remote and not self.dry_run:
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
        self.set_active_scenario(CANONICAL_BASELINE, sync_remote=True)

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
        output_subfolder: str = "ensayos_rack"
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
        os.makedirs(results_dir, exist_ok=True)

        print("\n" + "=" * 75)
        print(f" INICIANDO ENSAYO HIL EN RACK: {run_id}")
        print(f" - Escenario: {scenario_name}")
        print(f" - Duración: {steps} pasos ({steps * dt_s:.1f} s / {steps + 1} muestras esperadas)")
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

        try:
            # 1. Configurar escenario activo
            self.set_active_scenario(scenario_name, sync_remote=True)

            if sync_code and not self.dry_run:
                self.deployer.sync_code_to_all()

            if self.dry_run:
                print("\n[DRY RUN] Simulación en modo seco. No se ejecutan comandos en el clúster.")
                return experiment_meta

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
                step_dt=dt_s
            )

            t0 = time.perf_counter()
            server.run(max_steps=steps)
            elapsed_s = time.perf_counter() - t0
            print(f"\n[OK] Simulación completada: {steps} pasos en {elapsed_s:.2f} s.")

            # 5. Descargar telemetría desde nodo Monitor (10.0.0.155)
            print("\n[Paso 4/5] Extrayendo telemetría consolidada desde RPi 10.0.0.155...")
            monitor_node = next(n for n in self.deployer.nodes if n["ip"] == "10.0.0.155")
            remote_csv = f"{self.deployer.get_remote_dir(monitor_node)}/output_data/telemetry_monitor.csv"
            local_csv = os.path.join(results_dir, "telemetry_rack.csv")

            try:
                ssh = self.deployer._get_ssh_client(monitor_node)
                sftp = ssh.open_sftp()
                sftp.get(remote_csv, local_csv)
                sftp.close()
                ssh.close()
                file_size = os.path.getsize(local_csv)
                csv_sha256 = compute_sha256(local_csv)
                print(f"[OK] Telemetría descargada exitosamente:")
                print(f"     Archivo: {local_csv}")
                print(f"     Tamaño: {file_size} bytes")
                print(f"     SHA-256: {csv_sha256}")
                experiment_meta["telemetry"] = {
                    "path": local_csv,
                    "bytes": file_size,
                    "sha256": csv_sha256
                }
            except Exception as e:
                print(f"[ERROR] No se pudo transferir la telemetría: {e}")
                experiment_meta["telemetry_error"] = str(e)

            # 6. Generar manifiesto de la corrida
            manifest_file = os.path.join(results_dir, "manifest.json")
            experiment_meta["end_time"] = datetime.now().isoformat()
            experiment_meta["elapsed_seconds"] = elapsed_s
            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump(experiment_meta, f, indent=2)
            print(f"[OK] Manifiesto generado en: {manifest_file}")

        finally:
            # 7. Salvaguarda Incondicional: Parar contenedores y restaurar ACTIVO.txt
            print("\n[Paso 5/5] Ejecutando salvaguarda y detención de contenedores...")
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


def main():
    parser = argparse.ArgumentParser(description="Orquestador de Ensayos HIL en Rack Raspberry Pi")
    parser.add_argument(
        "--campaign",
        choices=["surplus-pair", "surplus-006", "surplus-007", "dynamic-005", "resilience-d25", "custom"],
        default="surplus-pair",
        help="Campaña o preset a ejecutar"
    )
    parser.add_argument("--steps", type=int, default=600, help="Número de pasos (default: 600 @ 2 Hz = 300 s)")
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

    args = parser.parse_args()
    orchestrator = RackExperimentOrchestrator(engine=args.engine, dry_run=args.dry_run)

    if args.campaign == "surplus-pair":
        print("\n>>> EJECUTANDO PAR EXCEDENTARIO COMPLETO (S-O-18 / Familia 2 D-24) <<<")
        # 1. ESC-HIL-006 (Excedente con ventana declarada)
        orchestrator.run_experiment(
            scenario_name="ESC-HIL-006_excedente_ventana_declarada",
            steps=args.steps,
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
            steps=args.steps,
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
            steps=args.steps,
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
            steps=args.steps,
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
            steps=args.steps,
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
            steps=args.steps,
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
            steps=args.steps,
            dt_s=args.dt,
            p_min_diesel=args.p_min_diesel,
            p_charge_max=args.p_charge_max,
            network_profile=args.network_profile,
            contingencies_file=args.contingencies_file,
            network_seed=args.seed,
            sync_code=args.sync,
            output_subfolder="custom"
        )


if __name__ == "__main__":
    main()
