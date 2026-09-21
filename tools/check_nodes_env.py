import paramiko

ips = ['10.0.0.152', '10.0.0.153', '10.0.0.154', '10.0.0.155']
for ip in ips:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, username='admin', password='Autonoma2018', timeout=5)
    cmd = "python3 -c 'import zmq; print(zmq.__version__)' 2>/dev/null || echo 'NO_ZMQ'"
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    print(f"{ip}: pyzmq -> {out}")
    ssh.close()
