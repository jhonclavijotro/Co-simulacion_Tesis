import subprocess
import os
import sys
import argparse
import json
import time
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from Docker.docker_compose_generator import DockerComposeGenerator


class RaspberryDeployer:
    """
    Automatizador de despliegue remoto SSH/SCP hacia la Raspberry Pi 5.
    Permite:
      - Diagnóstico de conexión SSH y estado de Docker en RPi 5.
      - Sincronización diferencial de archivos fuente excluyendo temporales.
      - Generación paramétrica de manifiestos docker-compose con esquemas Hold (ZOH, FOH, ZFOH).
      - Ejecución remota de contenedores y monitoreo de estado.
      - Pruebas de estrés y evaluación de desempeño multitasa.
    """
    def __init__(
        self,
        host: str = "192.168.1.10",
        user: str = "jhonclavijotro",
        port: int = 22,
        remote_dir: str = "/home/jhonclavijotro/Tesis_MAS_RPi",
        master_clock_host: str = "192.168.1.100",
        hold_mode: str = "ZOH",
        zfoh_lambda: float = 0.7
    ):
        self.host = host
        self.user = user
        self.port = port
        self.remote_dir = remote_dir
        self.master_clock_host = master_clock_host
        self.hold_mode = hold_mode.upper()
        self.zfoh_lambda = float(zfoh_lambda)

    def _run_ssh(self, remote_command: str, timeout: int = 15) -> Dict[str, Any]:
        """Ejecuta un comando vía SSH con timeout y captura de salidas."""
        ssh_cmd = [
            "ssh",
            "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=no",
            "-p", str(self.port),
            f"{self.user}@{self.host}",
            remote_command
        ]
        try:
            res = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
            return {
                "success": res.returncode == 0,
                "returncode": res.returncode,
                "stdout": res.stdout.strip(),
                "stderr": res.stderr.strip()
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "returncode": -1, "stdout": "", "stderr": "Timeout SSH excedido"}
        except Exception as e:
            return {"success": False, "returncode": -2, "stdout": "", "stderr": str(e)}

    def test_connection(self) -> Dict[str, Any]:
        """Verifica la conectividad SSH y disponibilidad de Docker en la Raspberry Pi 5."""
        print(f"Probando conexión SSH a {self.user}@{self.host}:{self.port}...")
        diag_cmd = "uname -m && which docker && docker --version"
        res = self._run_ssh(diag_cmd)
        
        if res["success"]:
            lines = res["stdout"].splitlines()
            arch = lines[0] if len(lines) > 0 else "Desconocida"
            docker_ver = lines[-1] if len(lines) > 1 else "No detectado"
            info = {
                "connected": True,
                "host": self.host,
                "user": self.user,
                "architecture": arch,
                "docker_version": docker_ver,
                "message": f"Conectado a Raspberry Pi 5 ({arch}) - {docker_ver}"
            }
            print(f"[OK] {info['message']}")
            return info
        else:
            info = {
                "connected": False,
                "host": self.host,
                "user": self.user,
                "architecture": None,
                "docker_version": None,
                "message": f"Fallo al conectar con RPi 5: {res['stderr'] or 'Host inalcanzable'}"
            }
            print(f"[AVISO] {info['message']}")
            return info

    def generate_rpi_manifest(self, output_path: str = "docker-compose.rpi.yml", network_profile: str = "IDEAL") -> str:
        """Genera un manifiesto docker-compose configurado para la Raspberry Pi."""
        topo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "topologia_BT_4nodos.csv"))
        gen = DockerComposeGenerator(topo_path)
        out = gen.generate_yaml(
            output_path=output_path,
            mode="ONLINE",
            network_profile=network_profile,
            hold_mode=self.hold_mode,
            zfoh_lambda=self.zfoh_lambda,
            master_clock_host=self.master_clock_host
        )
        print(f"[DESPLIEGUE RPi] Manifiesto generado en {out} (Hold: {self.hold_mode}, Lambda: {self.zfoh_lambda}, Master Clock: {self.master_clock_host})")
        return out

    def sync_code(self, local_dir: str = ".") -> Dict[str, Any]:
        """Sincroniza los módulos y configuraciones esenciales hacia la Raspberry Pi 5."""
        print(f"Sincronizando código hacia {self.user}@{self.host}:{self.remote_dir}...")
        
        # 1. Crear directorio remoto
        mkdir_res = self._run_ssh(f"mkdir -p {self.remote_dir}")
        if not mkdir_res["success"]:
            return {"success": False, "message": f"Error creando directorio remoto: {mkdir_res['stderr']}"}

        # 2. Generar manifiesto RPi localmente
        manifest_path = os.path.join(local_dir, "docker-compose.yml")
        self.generate_rpi_manifest(manifest_path)

        # 3. Directorios y archivos a sincronizar
        items_to_sync = ["config", "Docker", "Agents", "Solar", "Eolica", "Hidrica", "BESS", "Diesel", "Demanda", "mock_data", "common", "requirements.txt", "docker-compose.yml"]
        existing_items = [item for item in items_to_sync if os.path.exists(os.path.join(local_dir, item))]
        
        scp_items_str = " ".join([os.path.join(local_dir, item) for item in existing_items])
        scp_cmd = f"scp -P {self.port} -r {scp_items_str} {self.user}@{self.host}:{self.remote_dir}/"
        
        try:
            res = subprocess.run(scp_cmd, shell=True, capture_output=True, text=True, timeout=60)
            if res.returncode == 0:
                print("[OK] Sincronización de código completada.")
                return {"success": True, "message": "Archivos sincronizados exitosamente."}
            else:
                print(f"[AVISO] Error en SCP: {res.stderr}")
                return {"success": False, "message": res.stderr.strip()}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def deploy_docker(self) -> Dict[str, Any]:
        """Construye y levanta los 8 contenedores desacoplados en la Raspberry Pi 5."""
        print(f"Desplegando contenedores en Raspberry Pi 5...")
        remote_cmd = f"cd {self.remote_dir} && docker compose up -d --build"
        res = self._run_ssh(remote_cmd, timeout=120)
        
        if res["success"]:
            print(f"[OK] Contenedores desplegados:\n{res['stdout']}")
            return {"success": True, "output": res["stdout"], "message": "Contenedores Docker levantados en RPi 5"}
        else:
            print(f"[ERROR] Fallo en docker compose en RPi: {res['stderr']}")
            return {"success": False, "output": res["stderr"], "message": res["stderr"]}

    def get_cluster_status(self) -> Dict[str, Any]:
        """Consulta el estado de los contenedores en ejecución en la RPi."""
        res = self._run_ssh(f"cd {self.remote_dir} && docker compose ps --format json")
        if res["success"]:
            try:
                output = res["stdout"]
                containers = []
                for line in output.splitlines():
                    if line.strip():
                        try:
                            containers.append(json.loads(line))
                        except Exception:
                            pass
                return {"success": True, "containers": containers, "raw": output}
            except Exception:
                return {"success": True, "raw": res["stdout"]}
        return {"success": False, "message": res["stderr"]}

    def stop_docker(self) -> Dict[str, Any]:
        """Detiene los contenedores en la RPi."""
        res = self._run_ssh(f"cd {self.remote_dir} && docker compose down", timeout=30)
        return {"success": res["success"], "message": res["stdout"] if res["success"] else res["stderr"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Despliegue y Validación en Clúster Raspberry Pi 5")
    parser.add_argument("--host", default="192.168.1.10", help="Dirección IP de la Raspberry Pi")
    parser.add_argument("--user", default="jhonclavijotro", help="Usuario SSH en la Raspberry Pi")
    parser.add_argument("--port", type=int, default=22, help="Puerto SSH")
    parser.add_argument("--master-clock-host", default="192.168.1.100", help="IP del PC Central (Master Clock ZMQ)")
    parser.add_argument("--hold-mode", default="ZFOH", choices=["ZOH", "FOH", "ZFOH"], help="Esquema Hold")
    parser.add_argument("--lambda-val", type=float, default=0.7, help="Parámetro Lambda para ZFOH [0.0 - 1.0]")
    parser.add_argument("--action", default="all", choices=["test", "sync", "deploy", "stop", "status", "all"], help="Acción a realizar")
    args = parser.parse_args()

    deployer = RaspberryDeployer(
        host=args.host,
        user=args.user,
        port=args.port,
        master_clock_host=args.master_clock_host,
        hold_mode=args.hold_mode,
        zfoh_lambda=args.lambda_val
    )

    if args.action in ["test", "all"]:
        diag = deployer.test_connection()
        if not diag["connected"] and args.action == "all":
            print("\n[Instrucción de Despliegue Manual]:")
            print(f"1. Conectar RPi 5 a la red local.")
            print(f"2. Ejecutar: ssh {deployer.user}@{deployer.host}")
            print(f"3. Verificar que Docker esté instalado y en ejecución.")
            sys.exit(1)

    if args.action in ["sync", "all"]:
        deployer.sync_code()

    if args.action in ["deploy", "all"]:
        deployer.deploy_docker()

    if args.action == "status":
        st = deployer.get_cluster_status()
        print(json.dumps(st, indent=2))

    if args.action == "stop":
        deployer.stop_docker()
