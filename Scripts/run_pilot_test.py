import os
import sys
import time
import subprocess

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Scripts.cluster_deployer import ClusterDeployer
from Central_PC.power_flow_clock_server import PowerFlowClockServer

def main():
    steps = 30
    topo_csv = os.path.abspath("Forms/escenarios_generados/ESC-HIL-001_rampa_sombreado_demanda/topologia_red_8nodos.csv")
    
    print("=" * 70)
    print(" INICIANDO PRUEBA PILOTO DE CO-SIMULACIÓN (30 PASOS / 15 SEGUNDOS)")
    print(f" - Topología: {topo_csv}")
    print("=" * 70)

    deployer = ClusterDeployer("raspberry_list.md")

    # 1. Limpieza preventiva en el clúster
    print("\n[Paso 1/4] Asegurando estado limpio en todas las Raspberry Pis...")
    deployer.stop_cluster()
    time.sleep(1.0)

    # 2. Despliegue de contenedores en las 6 Raspberry Pis
    print(f"\n[Paso 2/4] Levantando contenedores Docker para {steps} pasos en el clúster...")
    deployer.start_cluster(steps=steps, engine="docker")
    print("Esperando 3 segundos para inicialización de sockets de borde...")
    time.sleep(3.0)

    # 3. Arranque del Servidor Central (Reloj Maestro ZMQ + Solver FBS 8 Nodos)
    print(f"\n[Paso 3/4] Iniciando Servidor Central PC (FBS 8 Nodos @ 400 V)...")
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

    # 4. Descargar y verificar telemetría desde RPi 5 (Monitor: 10.0.0.155)
    print("\n[Paso 4/4] Verificando telemetría capturada en RPi 5 (Nodo Monitor)...")
    monitor_node = [n for n in deployer.nodes if n["ip"] == "10.0.0.155"][0]
    remote_csv = f"{deployer.get_remote_dir(monitor_node)}/output_data/telemetry_monitor.csv"
    local_csv = os.path.abspath("output_data/telemetry_monitor_pilot_30steps.csv")
    os.makedirs("output_data", exist_ok=True)

    try:
        ssh = deployer._get_ssh_client(monitor_node)
        sftp = ssh.open_sftp()
        sftp.get(remote_csv, local_csv)
        sftp.close()
        ssh.close()
        print(f"[OK] Telemetría del monitor descargada exitosamente en:\n     {local_csv}")
        
        # Leer primeras y últimas líneas para diagnóstico
        with open(local_csv, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        print(f"     Total registros capturados: {len(lines)-1} pasos.")
        if len(lines) > 1:
            print(f"     Encabezado: {lines[0]}")
            print(f"     Paso final: {lines[-1]}")
    except Exception as e:
        print(f"[AVISO] No se pudo descargar telemetría remota: {e}")

    # 5. Detener contenedores
    print("\nDeteniendo contenedores en el clúster...")
    deployer.stop_cluster()
    print("\n" + "=" * 70)
    print(" PRUEBA PILOTO COMPLETADA EXITOSAMENTE")
    print("=" * 70)

if __name__ == "__main__":
    main()

