import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Scripts.cluster_deployer import ClusterDeployer
from Central_PC.power_flow_clock_server import PowerFlowClockServer

def main():
    steps = 600
    topo_csv = os.path.abspath("Forms/escenarios_generados/ESC-HIL-001_rampa_sombreado_demanda/topologia_red_8nodos.csv")
    
    print("=" * 70)
    print(" INICIANDO EXPERIMENTO FORMAL HIL EN CLÚSTER (600 PASOS / 300 SEGUNDOS / 5 MIN)")
    print(f" - Topología: {topo_csv}")
    print(f" - Servidor Web Dashboard: http://10.0.0.160:8000/web_dashboard.html")
    print("=" * 70)

    deployer = ClusterDeployer("raspberry_list.md")

    # 1. Limpieza preventiva
    print("\n[Paso 1/5] Preparando estado limpio en todas las Raspberry Pis...")
    deployer.stop_cluster()
    time.sleep(1.0)

    # 2. Despliegue de contenedores en las 6 Raspberry Pis
    print(f"\n[Paso 2/5] Levantando contenedores Docker para {steps} pasos en el clúster...")
    deployer.start_cluster(steps=steps, engine="docker")
    print("Esperando 3 segundos para inicialización de sockets de borde...")
    time.sleep(3.0)

    # 3. Arranque del Servidor Central (Reloj Maestro ZMQ + Solver FBS 8 Nodos)
    print(f"\n[Paso 3/5] Iniciando Servidor Central PC (FBS 8 Nodos @ 400 V)...")
    print(">>> PUEDES ABRIR EN TU NAVEGADOR: http://10.0.0.160:8000/web_dashboard.html <<<\n")
    server = PowerFlowClockServer(
        topology_path=topo_csv,
        v_base=400.0,
        s_base=10000.0,
        port_rep=5555,
        port_pub=5556,
        step_dt=0.5
    )
    
    start_t = time.perf_counter()
    server.run(max_steps=steps)
    elapsed = time.perf_counter() - start_t
    print(f"\n[OK] Servidor completó {steps} pasos en {elapsed:.2f} s.")

    # 4. Descargar telemetría desde RPi 5 (Monitor: 10.0.0.155) y DATA (10.0.0.160)
    print("\n[Paso 4/5] Descargando telemetría consolidada del experimento...")
    monitor_node = [n for n in deployer.nodes if n["ip"] == "10.0.0.155"][0]
    remote_csv = f"{deployer.get_remote_dir(monitor_node)}/output_data/telemetry_monitor.csv"
    local_csv = os.path.abspath("output_data/telemetry_monitor_cluster_8nodes_hil.csv")
    os.makedirs("output_data", exist_ok=True)

    try:
        ssh = deployer._get_ssh_client(monitor_node)
        sftp = ssh.open_sftp()
        sftp.get(remote_csv, local_csv)
        sftp.close()
        ssh.close()
        print(f"[OK] Telemetría del monitor guardada en:\n     {local_csv}")
    except Exception as e:
        print(f"[AVISO] Error descargando telemetría del monitor: {e}")

    # 5. Detener solo los contenedores de cómputo para dejar el Web Dashboard activo en DATA
    print("\n[Paso 5/5] Deteniendo contenedores de simulación...")
    stop_compute_cmd = "docker stop nodo_1_diesel nodo_2_solar nodo_3_bess nodos_cargas nodo_monitor_hil 2>/dev/null; docker rm -f nodo_1_diesel nodo_2_solar nodo_3_bess nodos_cargas nodo_monitor_hil 2>/dev/null; pkill -f distributed_node_runner; pkill -f multi_load_process; pkill -f monitor_node_service"
    for node in deployer.nodes:
        if node["ip"] != "10.0.0.160":
            try:
                ssh = deployer._get_ssh_client(node, timeout=4)
                ssh.exec_command(stop_compute_cmd)
                ssh.close()
            except Exception:
                pass

    print("[OK] Contenedores de cómputo detenidos.")
    print(">>> El Web Dashboard permanece ACTIVO en: http://10.0.0.160:8000/web_dashboard.html <<<")
    print("\n" + "=" * 70)
    print(" EXPERIMENTO FORMAL HIL DE 600 PASOS COMPLETADO CON ÉXITO")
    print("=" * 70)

if __name__ == "__main__":
    main()

