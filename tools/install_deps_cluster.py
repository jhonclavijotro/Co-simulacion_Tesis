import paramiko

nodes = [
    {"name": "MASTER_2", "ip": "10.0.0.151", "user": "admin", "password": "Autonoma2018"},
    {"name": "RP5-Nodo2A", "ip": "10.0.0.152", "user": "admin", "password": "Autonoma2018"},
    {"name": "RP5-Nodo2B", "ip": "10.0.0.153", "user": "admin", "password": "Autonoma2018"},
    {"name": "RP5-Nodo2C", "ip": "10.0.0.154", "user": "admin", "password": "Autonoma2018"},
    {"name": "RP5-Nodo2D", "ip": "10.0.0.155", "user": "admin", "password": "Autonoma2018"},
    {"name": "DATA", "ip": "10.0.0.160", "user": "jhonclavijotro", "password": "Jhonathan/7319"},
]

for node in nodes:
    ip = node["ip"]
    name = node["name"]
    user = node["user"]
    pwd = node["password"]
    print(f"Verificando / instalando dependencias en {name} ({ip})...")
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=user, password=pwd, timeout=5)
        cmd = f"echo '{pwd}' | sudo -S apt-get update -y >/dev/null 2>&1 && echo '{pwd}' | sudo -S apt-get install -y python3-zmq python3-numpy python3-scipy >/dev/null 2>&1; python3 -c 'import zmq, numpy; print(\"OK zmq:\", zmq.__version__, \"numpy:\", numpy.__version__)'"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        out = stdout.read().decode().strip()
        print(f"  {name} ({ip}): {out}")
        ssh.close()
    except Exception as e:
        print(f"  {name} ({ip}): Error -> {e}")

