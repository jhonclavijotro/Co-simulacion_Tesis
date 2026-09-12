import paramiko

nodes = ['10.0.0.152', '10.0.0.153', '10.0.0.154', '10.0.0.155']
for ip in nodes:
    print(f"Instalando python3-zmq en {ip}...")
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username='admin', password='Autonoma2018', timeout=5)
        cmd = "echo Autonoma2018 | sudo -S apt-get install -y python3-zmq >/dev/null 2>&1 && python3 -c 'import zmq; print(\"OK pyzmq:\", zmq.__version__)'"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        out = stdout.read().decode().strip()
        print(f"  {ip}: {out}")
        ssh.close()
    except Exception as e:
        print(f"  {ip}: Error -> {e}")
