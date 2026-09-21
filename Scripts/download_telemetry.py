import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from Scripts.cluster_deployer import ClusterDeployer

d = ClusterDeployer()
node = next(n for n in d.nodes if n['ip'] == '10.0.0.155')
remote_path = f"{d.get_remote_dir(node)}/output_data/telemetry_monitor.csv"
local_path = os.path.abspath("output_data/telemetry_monitor_cluster_rpi.csv")

print(f"Descargando {remote_path} -> {local_path}...")
ssh = d._get_ssh_client(node)
sftp = ssh.open_sftp()
sftp.get(remote_path, local_path)
sftp.close()
ssh.close()
print(f"Descarga exitosa. Tamano: {os.path.getsize(local_path)} bytes")
