import os
import sys
import re
import time
import socket
import argparse
from typing import List, Dict, Any

# Permitir ejecucion con entorno virtual o python del sistema
try:
    import paramiko
except ImportError:
    # Intentar cargar desde el virtualenv local si no esta en el sys.path
    venv_site = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".venv", "Lib", "site-packages"))
    if os.path.exists(venv_site):
        sys.path.insert(0, venv_site)
    import paramiko


def get_local_ip(target_subnet="10.0.0."):
    """Detecta la IP local del PC Central en la subred Ethernet."""
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if ip.startswith(target_subnet):
                return ip
    except Exception:
        pass
    return "10.0.0.156"


class ClusterDeployer:
    """
    Orquestador Multi-RPi para la Microrred Distribuida.
    Lee directamente 'raspberry_list.md' como Fuente Unica de Verdad y gestiona
    el despliegue en las 5 Raspberry Pi 5 y la comunicacion con el PC Central.
    """
    def __init__(self, list_path: str = "raspberry_list.md", remote_dir: str = "/home/admin/Desktop/test/Tesis_MAS_RPi"):
        self.list_path = os.path.abspath(list_path)
        self.remote_dir = remote_dir
        self.master_host = get_local_ip()
        self.nodes = self._parse_raspberry_list()

    def _parse_raspberry_list(self) -> List[Dict[str, Any]]:
        """Parsea dinamicamente el archivo markdown con la lista de Raspberry Pis."""
        if not os.path.exists(self.list_path):
            raise FileNotFoundError(f"No se encontro {self.list_path}")

        nodes = []
        pattern = re.compile(r"Raspberry denominada \*\*([^\*]+)\*\* tiene como user \*\*([^\*]+)\*\* en el puerto \*\*([0-9\.]+)\*\*\s*y contrase[ñn]a \*\*([^\*]+)\*\*", re.IGNORECASE)

        with open(self.list_path, "r", encoding="utf-8") as f:
            for line in f:
                match = pattern.search(line)
                if match:
                    name, user, ip, pwd = match.groups()
                    nodes.append({
                        "name": name.strip(),
                        "user": user.strip(),
                        "ip": ip.strip(),
                        "password": pwd.strip()
                    })

        # Asignacion de roles topologicos segun el plan
        # RPi 0 -> Nodo 1 (Diesel Slack)
        # RPi 1 -> Nodo 2 (Solar)
        # RPi 2 -> Nodo 3 (BESS)
        # RPi 3 -> Nodos 4,5,6 (3 Cargas)
        # RPi 4 -> Nodo Monitor
        roles = [
            {"role": "DIESEL_SLACK", "node_id": 1, "desc": "Nodo 1: Diesel (Slack en Isla)"},
            {"role": "SOLAR_PV",     "node_id": 2, "desc": "Nodo 2: Solar Fotovoltaico"},
            {"role": "BESS_STORAGE", "node_id": 3, "desc": "Nodo 3: BESS (Baterias)"},
            {"role": "LOADS_TRIPLE", "node_id": [4, 5, 6], "desc": "Nodos 4, 5, 6: 3 Cargas de Demanda"},
            {"role": "MONITOR_NODE", "node_id": "MON", "desc": "Nodo Monitor y Telemetria"}
        ]

        for i, node in enumerate(nodes):
            if i < len(roles):
                node.update(roles[i])
            else:
                node.update({"role": "EXTRA", "node_id": i+1, "desc": f"Nodo Extra {i+1}"})

        return nodes

    def _get_ssh_client(self, node: Dict[str, Any], timeout: int = 5) -> paramiko.SSHClient:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=node["ip"],
            port=22,
            username=node["user"],
            password=node["password"],
            timeout=timeout,
            banner_timeout=10
        )
        return ssh

    def test_connectivity(self) -> Dict[str, bool]:
        """Verifica la conectividad SSH y estado de Python/Docker en todo el cluster."""
        print("=" * 65)
        print(" DIAGNOSTICO DE CONECTIVIDAD DEL CLUSTER RASPBERRY PI 5")
        print("=" * 65)
        results = {}
        for node in self.nodes:
            ip = node["ip"]
            name = node["name"]
            desc = node["desc"]
            try:
                ssh = self._get_ssh_client(node, timeout=4)
                stdin, stdout, stderr = ssh.exec_command("hostname && python3 --version && docker --version 2>/dev/null || echo 'No Docker'")
                out = stdout.read().decode().strip().splitlines()
                hname = out[0] if len(out) > 0 else "N/A"
                py_ver = out[1] if len(out) > 1 else "N/A"
                doc_ver = out[2] if len(out) > 2 else "N/A"
                print(f"[OK] {name:12} ({ip}): Host={hname} | {py_ver} | {doc_ver} | Rol: {desc}")
                ssh.close()
                results[ip] = True
            except Exception as e:
                print(f"[FAIL] {name:12} ({ip}): Error -> {e} | Rol: {desc}")
                results[ip] = False
        return results

    def sync_code_to_all(self, local_root: str = "."):
        """Sincroniza el codigo fuente esencial del proyecto a cada Raspberry Pi."""
        print("\n" + "=" * 65)
        print(" SINCRONIZANDO CODIGO HACIA TODAS LAS RASPBERRY PI 5")
        print(f" Destino Remoto: {self.remote_dir}")
        print("=" * 65)

        items_to_sync = [
            "Agents", "Central_PC", "Solar", "Eolica", "Hidrica",
            "BESS", "Diesel", "Demanda", "config", "mock_data",
            "common", "requirements.txt", "raspberry_list.md"
        ]

        for node in self.nodes:
            ip = node["ip"]
            name = node["name"]
            print(f"\n--> Sincronizando {name} ({ip})...")
            try:
                ssh = self._get_ssh_client(node, timeout=3)
                sftp = ssh.open_sftp()

                # Crear estructura de carpetas remota
                ssh.exec_command(f"mkdir -p {self.remote_dir}")

                for item in items_to_sync:
                    local_item_path = os.path.join(local_root, item)
                    remote_item_path = f"{self.remote_dir}/{item}"

                    if not os.path.exists(local_item_path):
                        continue

                    if os.path.isfile(local_item_path):
                        sftp.put(local_item_path, remote_item_path)
                    elif os.path.isdir(local_item_path):
                        ssh.exec_command(f"mkdir -p {remote_item_path}")
                        for root, _, files in os.walk(local_item_path):
                            if "__pycache__" in root or ".git" in root:
                                continue
                            rel_root = os.path.relpath(root, local_item_path)
                            rem_sub = f"{remote_item_path}/{rel_root}".replace("\\", "/") if rel_root != "." else remote_item_path
                            ssh.exec_command(f"mkdir -p {rem_sub}")
                            for f in files:
                                if f.endswith(".pyc"):
                                    continue
                                local_f = os.path.join(root, f)
                                remote_f = f"{rem_sub}/{f}".replace("\\", "/")
                                sftp.put(local_f, remote_f)

                sftp.close()
                ssh.close()
                print(f"    [OK] {name} ({ip}) sincronizado exitosamente.")
            except Exception as e:
                print(f"    [AVISO] No se pudo sincronizar {name} ({ip}): {e}")

    def start_cluster(self, steps=None):
        """Inicia los servicios en cada Raspberry Pi segun su rol asignado."""
        print("\n" + "=" * 65)
        print(" INICIANDO SERVICIOS DEL CLUSTER (MODO ISLA - 13.8 kV)")
        print(f" - Servidor PC Central: {self.master_host}")
        print("=" * 65)

        steps_arg = f"--steps {steps}" if steps else ""

        commands = {
            "DIESEL_SLACK": f"cd {self.remote_dir} && nohup python3 Agents/distributed_node_runner.py --node-id 1 --source-type DIESEL --master-host {self.master_host} --p2p-port 6001 --neighbors 10.0.0.152:6002 --mode OFFLINE {steps_arg} > run_diesel.log 2>&1 &",
            "SOLAR_PV":     f"cd {self.remote_dir} && nohup python3 Agents/distributed_node_runner.py --node-id 2 --source-type SOLAR --master-host {self.master_host} --p2p-port 6002 --neighbors 10.0.0.151:6001 10.0.0.153:6003 --mode OFFLINE {steps_arg} > run_solar.log 2>&1 &",
            "BESS_STORAGE": f"cd {self.remote_dir} && nohup python3 Agents/distributed_node_runner.py --node-id 3 --source-type BESS --master-host {self.master_host} --p2p-port 6003 --neighbors 10.0.0.152:6002 --mode OFFLINE {steps_arg} > run_bess.log 2>&1 &",
            "LOADS_TRIPLE": f"cd {self.remote_dir} && nohup python3 Agents/multi_load_process.py --master-host {self.master_host} {steps_arg} > run_loads.log 2>&1 &",
            "MONITOR_NODE": f"cd {self.remote_dir} && nohup python3 Agents/monitor_node_service.py --master-host {self.master_host} {steps_arg} > run_monitor.log 2>&1 &"
        }

        for node in self.nodes:
            role = node["role"]
            cmd = commands.get(role)
            if not cmd:
                continue

            name = node["name"]
            ip = node["ip"]
            print(f"--> Arrancando en {name} ({ip}) [{role}]...")
            try:
                ssh = self._get_ssh_client(node)
                ssh.exec_command(cmd)
                ssh.close()
                print(f"    [OK] Proceso iniciado en {name}.")
            except Exception as e:
                print(f"    [FAIL] Error iniciando en {name}: {e}")

    def stop_cluster(self):
        """Detiene los procesos en ejecucion en todas las Raspberry Pis."""
        print("\n" + "=" * 65)
        print(" DETENIENDO TODOS LOS PROCESOS EN EL CLUSTER RPi")
        print("=" * 65)
        kill_cmd = "pkill -f distributed_node_runner; pkill -f multi_load_process; pkill -f monitor_node_service"

        for node in self.nodes:
            name = node["name"]
            ip = node["ip"]
            try:
                ssh = self._get_ssh_client(node, timeout=3)
                ssh.exec_command(kill_cmd)
                ssh.close()
                print(f"[OK] Procesos detenidos en {name} ({ip}).")
            except Exception as e:
                print(f"[FAIL] Error deteniendo en {name} ({ip}): {e}")

    def status_cluster(self):
        """Consulta los procesos activos en cada Raspberry Pi."""
        print("\n" + "=" * 65)
        print(" ESTADO DE PROCESOS EN EL CLUSTER RASPBERRY PI")
        print("=" * 65)
        chk_cmd = "pgrep -fl python3 | grep -E 'distributed_node_runner|multi_load_process|monitor_node_service' || echo 'SIN PROCESOS ACTIVOS'"

        for node in self.nodes:
            name = node["name"]
            ip = node["ip"]
            role = node["role"]
            try:
                ssh = self._get_ssh_client(node, timeout=3)
                stdin, stdout, stderr = ssh.exec_command(chk_cmd)
                out = stdout.read().decode().strip()
                print(f"\n[{name} ({ip}) - {role}]:")
                print(f"   {out}")
                ssh.close()
            except Exception as e:
                print(f"\n[{name} ({ip}) - {role}]: ERROR -> {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orquestador Multi-RPi para Microrred Distribuida")
    parser.add_argument("--action", default="test", choices=["test", "sync", "start", "stop", "status", "all"], help="Accion a ejecutar")
    parser.add_argument("--steps", type=int, default=None, help="Numero de pasos para --action start")
    parser.add_argument("--list-file", default="raspberry_list.md", help="Ruta al archivo raspberry_list.md")
    args = parser.parse_args()

    deployer = ClusterDeployer(list_path=args.list_file)

    if args.action in ["test", "all"]:
        deployer.test_connectivity()

    if args.action in ["sync", "all"]:
        deployer.sync_code_to_all()

    if args.action == "start":
        deployer.start_cluster(steps=args.steps)

    if args.action == "status":
        deployer.status_cluster()

    if args.action == "stop":
        deployer.stop_cluster()
