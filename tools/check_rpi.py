import socket
import paramiko
import sys
import io

# Forzar salida en utf-8 para terminal Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


rpi_list = [
    {"name": "MASTER_2", "ip": "10.0.0.151", "user": "admin", "password": "Autonoma2018"},
    {"name": "RP5-Nodo2A", "ip": "10.0.0.152", "user": "admin", "password": "Autonoma2018"},
    {"name": "RP5-Nodo2B", "ip": "10.0.0.153", "user": "admin", "password": "Autonoma2018"},
    {"name": "RP5-Nodo2C", "ip": "10.0.0.154", "user": "admin", "password": "Autonoma2018"},
    {"name": "RP5-Nodo2D", "ip": "10.0.0.155", "user": "admin", "password": "Autonoma2018"},
    {"name": "DATA", "ip": "10.0.0.160", "user": "jhonclavijotro", "password": "Jhonathan/7319"},
]

def check_rpi(pi):
    name = pi["name"]
    ip = pi["ip"]
    user = pi["user"]
    pwd = pi["password"]

    print(f"\n==========================================")
    print(f"Probando {name} ({ip})...")
    print(f"==========================================")

    # 1. Socket check
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3.0)
    res = s.connect_ex((ip, 22))
    s.close()
    if res != 0:
        print(f"❌ Error de red: Puerto 22 no accesible en {ip} (código {res})")
        return False, "Puerto 22 inaccesible"

    print(f"✔️ Puerto 22 accesible.")

    # 2. SSH check
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(ip, port=22, username=user, password=pwd, timeout=5.0)
        print(f"✔️ Conexión SSH autenticada exitosamente como '{user}'.")

        # Info general
        stdin, stdout, stderr = ssh.exec_command("hostname; uname -m; docker --version 2>/dev/null || echo 'Docker no detectado'")
        out = stdout.read().decode().strip().split("\n")
        print(f"   - Hostname reportado: {out[0] if len(out) > 0 else 'N/A'}")
        print(f"   - Arquitectura: {out[1] if len(out) > 1 else 'N/A'}")
        print(f"   - Docker: {out[2] if len(out) > 2 else 'N/A'}")

        # Crear ~/Desktop/test
        cmd_mkdir = "mkdir -p ~/Desktop/test && ls -ld ~/Desktop/test"
        stdin, stdout, stderr = ssh.exec_command(cmd_mkdir)
        err = stderr.read().decode().strip()
        out = stdout.read().decode().strip()

        if err:
            print(f"⚠️ Salida de error al crear ~/Desktop/test: {err}")
        else:
            print(f"✔️ Carpeta creada/verificada: {out}")

        ssh.close()
        return True, "OK"
    except Exception as e:
        print(f"❌ Error durante SSH: {e}")
        return False, str(e)

def main():
    results = {}
    for pi in rpi_list:
        success, msg = check_rpi(pi)
        results[pi["name"]] = (success, msg)

    print("\n\n" + "="*45)
    print("RESUMEN DE ESTADO DE LAS RASPBERRY PI")
    print("="*45)
    all_ok = True
    for name, (success, msg) in results.items():
        status = "✅ CONECTADO Y CONFIGURADO" if success else f"❌ FALLO ({msg})"
        print(f"{name:15}: {status}")
        if not success:
            all_ok = False

    if all_ok:
        print("\n🎉 Todas las Raspberry Pi fueron verificadas y la carpeta ~/Desktop/test fue creada.")
    else:
        print("\n⚠️ Algunas Raspberry Pi presentaron problemas de conexión.")

if __name__ == "__main__":
    main()
