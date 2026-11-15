import sys, os
sys.path.insert(0, os.path.abspath("."))
import paramiko
from Scripts.cluster_deployer import ClusterDeployer

deployer = ClusterDeployer("raspberry_list.md")
for node in deployer.nodes:
    name = node["name"]
    ip = node["ip"]
    role = node["role"]
    print("=" * 60)
    print(f"LOGS DE {name} ({ip}) - {role}")
    print("=" * 60)
    try:
        ssh = deployer._get_ssh_client(node, timeout=4)
        cname = "nodo_1_diesel" if "DIESEL" in role else ("nodo_2_solar" if "SOLAR" in role else ("nodo_3_bess" if "BESS" in role else ("nodos_cargas" if "LOADS" in role else ("nodo_monitor_hil" if "LOAD_IND" in role else "nodo_data_storage"))))
        stdin, stdout, stderr = ssh.exec_command(f"docker logs --tail 40 {cname} 2>/dev/null || cat {deployer.get_remote_dir(node)}/run_native.log 2>/dev/null || echo 'No log available'")
        print(stdout.read().decode())
        ssh.close()
    except Exception as e:
        print("Error:", e)
