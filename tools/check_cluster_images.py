import sys, os
sys.path.insert(0, os.path.abspath("."))
import paramiko
from Scripts.cluster_deployer import ClusterDeployer

deployer = ClusterDeployer("raspberry_list.md")
print(f"Master PC Host: {deployer.master_host}")
for node in deployer.nodes:
    name = node["name"]
    ip = node["ip"]
    role = node["role"]
    try:
        ssh = deployer._get_ssh_client(node, timeout=4)
        cmd = "docker images tesis-rpi:latest --format '{{.Repository}}:{{.Tag}} ({{.Size}})' 2>/dev/null; python3 -c 'import zmq; print(\"Native pyzmq:\", zmq.__version__)' 2>/dev/null || echo 'No native zmq'"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        out = stdout.read().decode().strip().splitlines()
        img = out[0] if len(out) > 0 and out[0] else "NO_DOCKER_IMAGE"
        zmq_v = out[1] if len(out) > 1 else "NO_ZMQ"
        print(f"[{name:12} ({ip}) - {role:12}]: Image: {img} | {zmq_v}")
        ssh.close()
    except Exception as e:
        print(f"[{name:12} ({ip}) - {role:12}]: Error -> {e}")
