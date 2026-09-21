import os
import sys
import time
import json
import pytest
import urllib.request
import urllib.parse
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from GUI.influx_telemetry import InfluxTelemetryLogger
from GUI.gui_command_center import GUICommandCenter
from GUI.server_dashboard import ReusableTCPServer, APIAndStaticHandler

def test_influx_telemetry_logger_and_export(tmp_path):
    logger = InfluxTelemetryLogger()
    logger.clear()

    v_sample = {
        "1": {"V_pu": 1.0, "V_volts": 400.0},
        "2": {"V_pu": 0.9995, "V_volts": 399.8}
    }
    p_sample = {
        "1": {"P": 25000.0, "Q": 5000.0},
        "2": {"P": 10000.0, "Q": 2000.0}
    }
    net_sample = {
        "profile": "INDUSTRIAL_WIFI",
        "avg_delay_ms": 35.2,
        "packet_loss_ratio": 0.05,
        "total_sent": 100,
        "total_dropped": 5
    }

    rec1 = logger.log_step(1, "ONLINE", v_sample, p_sample, net_sample)
    assert rec1["step"] == 1
    assert rec1["network_stats"]["profile"] == "INDUSTRIAL_WIFI"
    assert len(logger.local_log) == 1

    rec2 = logger.log_step(2, "ONLINE", v_sample, p_sample, net_sample)
    assert rec2["step"] == 2
    assert len(logger.local_log) == 2

    # Probar exportación a JSON
    json_path = str(tmp_path / "telemetry_test.json")
    exported_json = logger.export_to_json(json_path)
    assert os.path.exists(exported_json)
    with open(exported_json, "r", encoding="utf-8") as f:
        loaded_json = json.load(f)
    assert len(loaded_json) == 2

    # Probar exportación a CSV
    csv_path = str(tmp_path / "telemetry_test.csv")
    exported_csv = logger.export_to_csv(csv_path)
    assert os.path.exists(exported_csv)
    with open(exported_csv, "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) >= 3  # Header + al menos 2 filas de nodos
    assert "net_profile" in lines[0]
    assert "INDUSTRIAL_WIFI" in lines[1]

    logger.clear()
    assert len(logger.local_log) == 0
    logger.close()

def test_gui_command_center_async_and_state(tmp_path):
    center = GUICommandCenter(
        mode="ONLINE",
        solver_mode="SENSITIVITY",
        mesh_type="RING_ZBUS",
        network_profile="INDUSTRIAL_WIFI"
    )

    # Actualización de parámetros
    center.set_mode("OFFLINE")
    assert center.mode == "OFFLINE"
    center.set_solver_mode("FBS")
    assert center.solver_mode == "FBS"
    center.set_mesh_type("FULL_JACOBIAN")
    assert center.mesh_type == "FULL_JACOBIAN"
    center.set_network_profile("SEVERE_STRESS")
    assert center.network_profile == "SEVERE_STRESS"

    # Generación de Manifiesto Docker
    compose_path = str(tmp_path / "docker-compose.test.yml")
    manifest = center.deploy_containers(compose_path)
    assert os.path.exists(manifest)

    # Captura de estado
    state = center.get_current_state()
    assert state["mode"] == "OFFLINE"
    assert state["network_profile"] == "SEVERE_STRESS"
    assert "voltages" in state["latest_result"]

    # Simulación asíncrona por 2 pasos
    started = center.start_simulation_thread(max_steps=2, step_delay=0.1)
    assert started is True
    time.sleep(0.35)
    center.stop_simulation()
    assert center.is_simulation_active() is False

    # Exportación
    export_csv = str(tmp_path / "session_export.csv")
    out = center.export_session_data(export_csv, fmt="csv")
    assert os.path.exists(out)

def test_server_dashboard_api_endpoints():
    # Iniciar un servidor de pruebas en un puerto efímero libre
    port = 8999
    httpd = None
    for p in range(8990, 9050):
        try:
            httpd = ReusableTCPServer(("127.0.0.1", p), APIAndStaticHandler)
            port = p
            break
        except Exception:
            continue

    assert httpd is not None, "No se pudo iniciar el servidor TCP de prueba"

    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.1)

    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. GET /api/telemetry/live
        req = urllib.request.Request(f"{base_url}/api/telemetry/live")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "latest_result" in data
            assert "network_profile" in data

        # 2. POST /api/config
        config_payload = json.dumps({
            "mode": "ONLINE",
            "solver_mode": "SENSITIVITY",
            "mesh_type": "RING_ZBUS",
            "network_profile": "LAN_ETHERNET",
            "topology": "BT"
        }).encode("utf-8")
        req_cfg = urllib.request.Request(
            f"{base_url}/api/config",
            data=config_payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req_cfg) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "success"

        # 3. POST /api/deploy
        req_dep = urllib.request.Request(
            f"{base_url}/api/deploy",
            data=b"{}",
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req_dep) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "success"
            assert "manifest" in data

        # 4. POST /api/simulation/start y /api/simulation/stop
        req_start = urllib.request.Request(
            f"{base_url}/api/simulation/start",
            data=b"{}",
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req_start) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "success"

        time.sleep(0.2)

        req_stop = urllib.request.Request(
            f"{base_url}/api/simulation/stop",
            data=b"{}",
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req_stop) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "success"

        # 5. GET /api/export
        req_exp = urllib.request.Request(f"{base_url}/api/export")
        with urllib.request.urlopen(req_exp) as resp:
            assert resp.status == 200
            assert "text/csv" in resp.headers.get("Content-Type", "")
            csv_content = resp.read().decode("utf-8")
            assert "step,timestamp,mode" in csv_content

    finally:
        httpd.shutdown()
        httpd.server_close()
