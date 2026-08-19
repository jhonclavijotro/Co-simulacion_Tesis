import subprocess
import os
import sys

class RaspberryDeployer:
    """
    Automatizador de despliegue remoto SSH/SCP hacia la Raspberry Pi 5.
    Host: 192.168.1.10
    User: jhonclavijotro
    """
    def __init__(self, host="192.168.1.10", user="jhonclavijotro", remote_dir="/home/jhonclavijotro/Tesis_MAS_RPi"):
        self.host = host
        self.user = user
        self.remote_dir = remote_dir

    def test_connection(self):
        """Verifica la conectividad SSH con la Raspberry Pi 5."""
        cmd = f'ssh -o ConnectTimeout=5 {self.user}@{self.host} "echo Conexión SSH Exitosa en RPi 5"'
        print(f"Probando conexión SSH a {self.user}@{self.host}...")
        try:
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                print(f"[OK] {res.stdout.strip()}")
                return True
            else:
                print(f"[Aviso] No se completó la conexión SSH directa: {res.stderr.strip()}")
                return False
        except Exception as e:
            print(f"[Aviso] Error en comando SSH: {e}")
            return False

    def sync_code(self, local_dir="."):
        """Sincroniza el código del proyecto hacia la Raspberry Pi 5."""
        print(f"Sincronizando código desde {local_dir} hacia {self.user}@{self.host}:{self.remote_dir}...")
        mkdir_cmd = f'ssh {self.user}@{self.host} "mkdir -p {self.remote_dir}"'
        subprocess.run(mkdir_cmd, shell=True, capture_output=True)

        scp_cmd = f'scp -r config Docker Agents mock_data Common {self.user}@{self.host}:{self.remote_dir}/'
        res = subprocess.run(scp_cmd, shell=True, capture_output=True, text=True)
        return res.returncode == 0

    def deploy_docker(self):
        """Ejecuta docker-compose en la Raspberry Pi 5."""
        print(f"Desplegando contenedores Docker en Raspberry Pi 5...")
        cmd = f'ssh {self.user}@{self.host} "cd {self.remote_dir} && docker compose up -d --build"'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        print(res.stdout)
        return res.returncode == 0

if __name__ == "__main__":
    deployer = RaspberryDeployer()
    connected = deployer.test_connection()
    if connected:
        deployer.sync_code()
        deployer.deploy_docker()
    else:
        print("\n[Instrucción de Despliegue Manual / Semimanual]:")
        print(f"1. Desde la terminal, ejecutar: ssh {deployer.user}@{deployer.host}")
        print(f"2. Ingresar la contraseña: Jhonathan/7319")
        print(f"3. Clonar/Copiar la carpeta del proyecto a {deployer.remote_dir}")
        print(f"4. Ejecutar: docker compose -f docker-compose.yml up -d --build")
