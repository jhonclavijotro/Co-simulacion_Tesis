#!/usr/bin/env python3
"""Despliegue del proyecto MAS en Raspberry Pi via SCP/SSH.

Uso:
  python deploy.py                    # despliega codigo via SCP
  python deploy.py --docker-build    # construye imagenes Docker en RPi
  python deploy.py --docker-run      # ejecuta docker-compose en RPi
"""

import argparse
import os
import subprocess
import sys
import time

RPI_USER = "jhonclavijotro"
RPI_HOST = "192.168.1.10"
RPI_DIR = "/home/jhonclavijotro/mas"
PLINK = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "plink.exe")
PSCP = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "pscp.exe")
HOSTKEY = "ssh-ed25519 255 SHA256:58xLuFJZciF8FRl9OH7+j0dxTaJDDTLqZD9cfBTPKzk"
PASSWORD = "Jhonathan/7319"


def _descargar_putty():
    if not os.path.exists(PLINK):
        import urllib.request
        url = "https://the.earth.li/~sgtatham/putty/0.83/w64/plink.exe"
        urllib.request.urlretrieve(url, PLINK)
        print(f"plink.exe descargado")
    if not os.path.exists(PSCP):
        import urllib.request
        url = "https://the.earth.li/~sgtatham/putty/0.83/w64/pscp.exe"
        urllib.request.urlretrieve(url, PSCP)
        print(f"pscp.exe descargado")


def ssh(comando):
    cmd = [PLINK, "-ssh", "-l", RPI_USER, "-pw", PASSWORD,
           "-batch", "-hostkey", HOSTKEY, RPI_HOST, comando]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f"SSH error: {r.stderr[:200] if r.stderr else r.stdout[:200]}")
    return r.stdout


def scp(origen, destino):
    cmd = [PSCP, "-scp", "-l", RPI_USER, "-pw", PASSWORD,
           "-hostkey", HOSTKEY, "-r", origen,
           f"{RPI_USER}@{RPI_HOST}:{destino}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(f"SCP error: {r.stderr[:200] if r.stderr else r.stdout[:200]}")
    return r.stdout


def deploy():
    _descargar_putty()
    print(f"Conectando a {RPI_USER}@{RPI_HOST}...")
    out = ssh("hostname; mkdir -p " + RPI_DIR)
    print(f"RPi: {out.strip()}")

    proyecto = os.path.dirname(os.path.abspath(__file__))
    exclude = [".git", "__pycache__", ".pyc", ".gitignore"]
    print(f"Copiando {proyecto}/ -> {RPI_DIR}/ ...")
    out = scp(proyecto + "/*", RPI_DIR)
    print(f"SCP: {out[:200] if out else 'ok'}")

    out = ssh(f"ls -la {RPI_DIR}/")
    print(f"Archivos en RPi:\n{out}")


def docker_build():
    _descargar_putty()
    print("Construyendo imagenes Docker en RPi...")
    ssh(f"cd {RPI_DIR} && docker compose -f Docker/docker-compose.yml build")
    print("Build completado")


def docker_run():
    _descargar_putty()
    print("Iniciando contenedores en RPi...")
    ssh(f"cd {RPI_DIR} && docker compose -f Docker/docker-compose.yml up -d")
    print("Contenedores iniciados. Estado:")
    out = ssh(f"cd {RPI_DIR} && docker compose -f Docker/docker-compose.yml ps")
    print(out)


def main():
    parser = argparse.ArgumentParser(description="Despliegue MAS en RPi")
    parser.add_argument("--docker-build", action="store_true")
    parser.add_argument("--docker-run", action="store_true")
    args = parser.parse_args()

    if args.docker_build:
        docker_build()
    elif args.docker_run:
        docker_run()
    else:
        deploy()


if __name__ == "__main__":
    main()
