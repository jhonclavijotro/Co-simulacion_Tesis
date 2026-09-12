import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('10.0.0.152', username='admin', password='Autonoma2018', timeout=5)
cmd = "ssh -o ConnectTimeout=2 -o StrictHostKeyChecking=no admin@10.0.0.151 2>&1"
stdin, stdout, stderr = ssh.exec_command(cmd)
print("Salida desde 152:")
print(stdout.read().decode())
err = stderr.read().decode()
if err:
    print("Stderr:", err)
ssh.close()
