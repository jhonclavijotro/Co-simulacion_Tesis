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
    def __init__(self, list_path: str = "raspberry_list.md", base_folder_name: str = "Tesis_MAS_RPi"):
        self.list_path = os.path.abspath(list_path)
        self.base_folder_name = base_folder_name
        self.master_host = get_local_ip()
        self.nodes = self._parse_raspberry_list()

    def get_remote_dir(self, node: Dict[str, Any]) -> str:
        """Calcula el directorio remoto correspondiente segun el usuario del nodo."""
        return f"/home/{node['user']}/Desktop/test/{self.base_folder_name}"

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

        # Asignacion de roles topologicos segun la distribucion de hardware:
        # RPi 0 -> Nodo 1 (Diesel Slack) - 10.0.0.151
        # RPi 1 -> Nodo 2 (Solar PV) - 10.0.0.152
        # RPi 2 -> Nodo 3 (BESS Storage) - 10.0.0.153
        # RPi 3 -> Nodos 4 y 5 (Cargas Residencial y Comercial) - 10.0.0.154
        # RPi 4 -> Nodo 6 (Carga Industrial / Demandas) - 10.0.0.155
        # RPi 5 -> DATA (Almacenamiento de Datos y Dashboard Web) - 10.0.0.160
        roles = [
            {"role": "DIESEL_SLACK", "node_id": 1, "desc": "Nodo 1: Generador Diesel (Slack en Isla)"},
            {"role": "SOLAR_PV",     "node_id": 2, "desc": "Nodo 2: Solar Fotovoltaico (PV)"},
            {"role": "BESS_STORAGE", "node_id": 3, "desc": "Nodo 3: BESS (Almacenamiento en Baterias)"},
            {"role": "LOADS_RES_COM", "node_id": [4, 5], "desc": "Nodos 4 y 5: Cargas Residencial y Comercial"},
            {"role": "LOAD_IND",     "node_id": 6, "desc": "Nodo 6: Carga Industrial"},
            {"role": "DATA_STORAGE", "node_id": "DATA", "desc": "Nodo DATA: Almacenamiento y Dashboard Web"}
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
        print(" SINCRONIZANDO CODIGO HACIA TODAS LAS RASPBERRY PI")
        print("=" * 65)

        items_to_sync = [
            "Agents", "Central_PC", "Solar", "Eolica", "Hidrica",
            "BESS", "Diesel", "Demanda", "config", "mock_data",
            "Forms", "Docker", "common", "requirements.txt", "raspberry_list.md", "GUI"
        ]

        for node in self.nodes:
            ip = node["ip"]
            name = node["name"]
            remote_dir = self.get_remote_dir(node)
            print(f"\n--> Sincronizando {name} ({ip}) en {remote_dir}...")
            try:
                ssh = self._get_ssh_client(node, timeout=5)
                sftp = ssh.open_sftp()

                # Crear estructura de carpetas remota
                ssh.exec_command(f"mkdir -p {remote_dir}")

                for item in items_to_sync:
                    local_item_path = os.path.join(local_root, item)
                    remote_item_path = f"{remote_dir}/{item}"

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

    def build_images(self):
        """Compila la imagen Docker 'tesis-rpi:latest' en todas las Raspberry Pi (ARM64)."""
        print("\n" + "=" * 65)
        print(" COMPILANDO IMAGENES DOCKER EN LAS 6 RASPBERRY PI (ARM64)")
        print("=" * 65)

        for node in self.nodes:
            name = node["name"]
            ip = node["ip"]
            remote_dir = self.get_remote_dir(node)
            print(f"\n--> Compilando imagen Docker en {name} ({ip})...")
            try:
                ssh = self._get_ssh_client(node, timeout=10)
                cmd = f"cd {remote_dir} && docker build -t tesis-rpi:latest -f Docker/Dockerfile.rpi ."
                stdin, stdout, stderr = ssh.exec_command(cmd)
                for line in iter(stdout.readline, ""):
                    line_s = line.strip()
                    if "Step" in line_s or "DONE" in line_s or "naming to" in line_s or "writing image" in line_s:
                        print(f"    [{name}] {line_s}")
                exit_status = stdout.channel.recv_exit_status()
                if exit_status == 0:
                    print(f"    [OK] Imagen Docker compilada exitosamente en {name}.")
                else:
                    err = stderr.read().decode().strip()
                    print(f"    [FAIL] Error compilando en {name}: {err}")
                ssh.close()
            except Exception as e:
                print(f"    [ERROR] Fallo en conexion a {name}: {e}")

    def start_cluster(self, steps=None, engine="docker"):
        """Inicia los servicios en cada Raspberry Pi segun su rol asignado (Docker o Nativo)."""
        print("\n" + "=" * 65)
        print(f" INICIANDO SERVICIOS DEL CLUSTER (MODO: {engine.upper()} - 13.8 kV)")
        print(f" - Servidor PC Central: {self.master_host}")
        print("=" * 65)

        steps_arg = f"--steps {steps}" if steps else ""

        for node in self.nodes:
            role = node["role"]
            name = node["name"]
            ip = node["ip"]
            remote_dir = self.get_remote_dir(node)

            py_cmd = None
            cname = None

            if role == "DIESEL_SLACK":
                cname = "nodo_1_diesel"
                py_cmd = f"python3 Agents/distributed_node_runner.py --node-id 1 --source-type DIESEL --master-host {self.master_host} --p2p-port 6001 --neighbors 10.0.0.152:6002 --mode OFFLINE {steps_arg}"
            elif role == "SOLAR_PV":
                cname = "nodo_2_solar"
                py_cmd = f"python3 Agents/distributed_node_runner.py --node-id 2 --source-type SOLAR --master-host {self.master_host} --p2p-port 6002 --neighbors 10.0.0.151:6001 10.0.0.153:6003 --mode OFFLINE {steps_arg}"
            elif role == "BESS_STORAGE":
                cname = "nodo_3_bess"
                py_cmd = f"python3 Agents/distributed_node_runner.py --node-id 3 --source-type BESS --master-host {self.master_host} --p2p-port 6003 --neighbors 10.0.0.152:6002 --mode OFFLINE {steps_arg}"
            elif role in ["LOADS_RES_COM", "LOADS_TRIPLE"]:
                cname = "nodos_cargas"
                py_cmd = f"python3 Agents/multi_load_process.py --master-host {self.master_host} {steps_arg}"
            elif role == "LOAD_IND":
                cname = "nodo_monitor_hil"
                py_cmd = f"python3 Agents/monitor_node_service.py --master-host {self.master_host} {steps_arg}"
            elif role == "DATA_STORAGE":
                cname = "nodo_data_storage"
                py_cmd = f"python3 GUI/rpi_dashboard_service.py --master-host {self.master_host} --web-port 8000 {steps_arg}"

            if not py_cmd:
                continue

            if engine == "docker":
                final_cmd = f"docker rm -f {cname} 2>/dev/null; docker run -d --name {cname} --network host -v {remote_dir}:/app tesis-rpi:latest {py_cmd}"
            else:
                final_cmd = f"cd {remote_dir} && nohup {py_cmd} > run_native.log 2>&1 &"

            print(f"--> Arrancando en {name} ({ip}) [{role}] ({engine})...")
            try:
                ssh = self._get_ssh_client(node)
                stdin, stdout, stderr = ssh.exec_command(final_cmd)
                out = stdout.read().decode().strip()
                err = stderr.read().decode().strip()
                ssh.close()
                if engine == "docker" and out:
                    print(f"    [OK] Contenedor {cname} ({out[:12]}) iniciado en {name}.")
                    if role == "DATA_STORAGE":
                        print(f"    [WEB] Dashboard disponible en: http://{ip}:8000/web_dashboard.html")
                else:
                    print(f"    [OK] Proceso iniciado en {name}.")
                    if role == "DATA_STORAGE":
                        print(f"    [WEB] Dashboard disponible en: http://{ip}:8000/web_dashboard.html")
            except Exception as e:
                print(f"    [FAIL] Error iniciando en {name}: {e}")

    def stop_cluster(self):
        """Detiene contenedores Docker y procesos nativos en todas las Raspberry Pis."""
        print("\n" + "=" * 65)
        print(" DETENIENDO TODOS LOS CONTENEDORES Y PROCESOS EN EL CLUSTER RPi")
        print("=" * 65)
        stop_cmd = "docker stop nodo_1_diesel nodo_2_solar nodo_3_bess nodos_cargas nodo_monitor_hil nodo_data_storage 2>/dev/null; docker rm -f nodo_1_diesel nodo_2_solar nodo_3_bess nodos_cargas nodo_monitor_hil nodo_data_storage 2>/dev/null; pkill -f distributed_node_runner; pkill -f multi_load_process; pkill -f monitor_node_service; pkill -f rpi_dashboard_service"

        for node in self.nodes:
            name = node["name"]
            ip = node["ip"]
            try:
                ssh = self._get_ssh_client(node, timeout=5)
                ssh.exec_command(stop_cmd)
                ssh.close()
                print(f"[OK] Contenedores y procesos detenidos en {name} ({ip}).")
            except Exception as e:
                print(f"[FAIL] Error deteniendo en {name} ({ip}): {e}")

    def status_cluster(self):
        """Consulta los contenedores Docker y procesos activos en cada Raspberry Pi."""
        print("\n" + "=" * 65)
        print(" ESTADO DE CONTENEDORES DOCKER Y PROCESOS EN EL CLUSTER RPi")
        print("=" * 65)
        chk_cmd = "echo '--- CONTENEDORES DOCKER ---' && (docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' || echo 'Error Docker') && echo '--- PROCESOS NATIVOS ---' && (pgrep -fl python3 | grep -E 'distributed_node_runner|multi_load_process|monitor_node_service|rpi_dashboard_service' || echo 'Ninguno')"

        for node in self.nodes:
            name = node["name"]
            ip = node["ip"]
            role = node["role"]
            try:
                ssh = self._get_ssh_client(node, timeout=5)
                stdin, stdout, stderr = ssh.exec_command(chk_cmd)
                out = stdout.read().decode().strip()
                print(f"\n[{name} ({ip}) - {role}]:")
                print(f"   {out}")
                ssh.close()
            except Exception as e:
                print(f"\n[{name} ({ip}) - {role}]: ERROR -> {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orquestador Multi-RPi para Microrred Distribuida")
    parser.add_argument("--action", default="test", choices=["test", "sync", "build", "start", "stop", "status", "all"], help="Accion a ejecutar")
    parser.add_argument("--engine", default="docker", choices=["docker", "native"], help="Motor de ejecucion (docker o native)")
    parser.add_argument("--steps", type=int, default=None, help="Numero de pasos para --action start")
    parser.add_argument("--list-file", default="raspberry_list.md", help="Ruta al archivo raspberry_list.md")
    args = parser.parse_args()

    deployer = ClusterDeployer(list_path=args.list_file)

    if args.action in ["test", "all"]:
        deployer.test_connectivity()

    if args.action in ["sync", "all"]:
        deployer.sync_code_to_all()

    if args.action in ["build", "all"]:
        deployer.build_images()

    if args.action == "start":
        deployer.start_cluster(steps=args.steps, engine=args.engine)

    if args.action == "status":
        deployer.status_cluster()

    if args.action == "stop":
        deployer.stop_cluster()

