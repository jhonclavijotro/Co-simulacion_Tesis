import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('10.0.0.151', username='admin', password='Autonoma2018', timeout=5)

# 1. Instalar python3-zmq
stdin, stdout, stderr = ssh.exec_command("echo Autonoma2018 | sudo -S apt-get install -y python3-zmq")
status = stdout.channel.recv_exit_status()
print(f"Instalacion finalizada con estado: {status}")

# 2. Verificar zmq
cmd = 'python3 -c "import zmq; print(zmq.__version__)"'
stdin, stdout, stderr = ssh.exec_command(cmd)
stdout.channel.recv_exit_status()
ver = stdout.read().decode().strip()
print(f"MASTER_2 (10.0.0.151): pyzmq instalado exitosamente -> v{ver}")
ssh.close()
