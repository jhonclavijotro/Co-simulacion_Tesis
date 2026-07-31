"""Despliegue del agente solar en Raspberry Pi.

Copia los archivos necesarios y lanza el agente solar.
Uso:
  python deploy_rpi_solar.py [--run]
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RPI_HOST = "192.168.1.11"
RPI_USER = "jhonclavijotro"
RPI_PASS = "Jhonathan/7319"
RPI_DIR = "/home/jhonclavijotro/mas_solar"
PC_HOST = "192.168.1.6"
PC_PORT = 5000

FILES_TO_COPY = [
    "Solar/SolarSimplificado.py",
    "MAS/agente_zmq.py",
    "MAS/cliente_dinamica.py",
    "ejecutar_agente_solar.py",
]


def scp(sftp, local, remote):
    sftp.put(local, remote)
    print(f"  {local} -> {remote}")


def main():
    parser = argparse.ArgumentParser(description="Despliegue solar en RPi")
    parser.add_argument("--run", action="store_true",
                        help="Ejecutar agente solar en RPi tras copiar")
    args = parser.parse_args()

    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Conectando a {RPI_USER}@{RPI_HOST}...")
    client.connect(RPI_HOST, username=RPI_USER, password=RPI_PASS, timeout=10)

    sftp = client.open_sftp()
    try:
        sftp.stat(RPI_DIR)
    except FileNotFoundError:
        sftp.mkdir(RPI_DIR)

    raiz = os.path.dirname(os.path.abspath(__file__))
    for fname in FILES_TO_COPY:
        local = os.path.join(raiz, fname)
        remote = RPI_DIR + "/" + fname
        rem_dir = remote.rsplit("/", 1)[0]
        stdin, stdout, stderr = client.exec_command(
            f"mkdir -p {rem_dir}")
        stdout.channel.recv_exit_status()
        scp(sftp, local, remote)

    sftp.close()
    print("Archivos copiados correctamente.")

    if args.run:
        print(f"\nIniciando agente solar en RPi (background)...")
        client.exec_command(
            f"cd {RPI_DIR} && nohup python3 ejecutar_agente_solar.py "
            f"--id 2 --host {PC_HOST} --puerto {PC_PORT} "
            f"--P_rated 3000 --modo local "
            f"> ~/solar_agent.log 2>&1 &",
        )
        time.sleep(1)
        stdin, stdout, stderr = client.exec_command(
            f"ps aux | grep ejecutar_agente_solar | grep -v grep"
        )
        proc = stdout.read().decode().strip()
        if proc:
            print(f"Agente solar PID: {proc.split()[1]}")
        else:
            stdin2, stdout2, stderr2 = client.exec_command(
                f"tail -5 ~/solar_agent.log")
            print(f"Log:\n{stdout2.read().decode()[:300]}")

    client.close()
    print("Despliegue completado.")


if __name__ == "__main__":
    main()
