import paramiko
import sys

# Ensure UTF-8 output
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    ssh.connect('10.0.0.151', username='admin', password='Autonoma2018', timeout=5)
    commands = [
        "python3 --version",
        "python3 -c 'import zmq; print(\"pyzmq:\", zmq.__version__)' 2>/dev/null || echo 'pyzmq: not installed'",
        "python3 -c 'import numpy; print(\"numpy:\", numpy.__version__)' 2>/dev/null || echo 'numpy: not installed'",
        "docker images",
        "ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1 && echo 'Internet: OK' || echo 'Internet: NO INTERNET'",
        "ip -4 addr show eth0 | grep inet"
    ]
    full_cmd = " && ".join(commands)
    stdin, stdout, stderr = ssh.exec_command(full_cmd)
    print("Salida diagnostico 10.0.0.151:")
    print(stdout.read().decode())
    err = stderr.read().decode()
    if err:
        print("Stderr:", err)
    ssh.close()
except Exception as e:
    print(f"Error: {e}")
