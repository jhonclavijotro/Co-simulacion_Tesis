import http.server
import socketserver
import os
import webbrowser
import sys
import json
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from GUI.gui_command_center import GUICommandCenter

DIRECTORY = os.path.dirname(os.path.abspath(__file__))

# Instancia global del motor del Centro de Mando
command_center = GUICommandCenter()

class APIAndStaticHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def _send_json_response(self, data: dict, status_code: int = 200):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path == "/api/telemetry/live":
            state = command_center.get_current_state()
            self._send_json_response(state)
            return

        elif parsed.path == "/api/export":
            # Generar exportación CSV en carpeta output_data
            export_path = os.path.abspath(os.path.join(DIRECTORY, "..", "output_data", "telemetry_session_export.csv"))
            command_center.export_session_data(export_path, fmt="csv")
            
            if os.path.exists(export_path):
                with open(export_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="telemetry_session_export.csv"')
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            else:
                self._send_json_response({"error": "No data to export"}, 404)
                return

        # Servir archivos estáticos del dashboard
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        
        try:
            req_data = json.loads(body) if body else {}
        except Exception:
            req_data = {}

        if parsed.path == "/api/config":
            if "mode" in req_data:
                command_center.set_mode(req_data["mode"])
            if "solver_mode" in req_data:
                command_center.set_solver_mode(req_data["solver_mode"])
            if "mesh_type" in req_data:
                command_center.set_mesh_type(req_data["mesh_type"])
            if "network_profile" in req_data:
                command_center.set_network_profile(req_data["network_profile"])
            if "topology" in req_data:
                topo_map = {
                    "BT": "topologia_BT_4nodos.csv",
                    "BT_MALLADA": "topologia_BT_mallada_4nodos.csv",
                    "MT": "topologia_MT_Nnodos.csv"
                }
                filename = topo_map.get(req_data["topology"], req_data["topology"])
                topo_path = os.path.abspath(os.path.join(DIRECTORY, "..", "config", filename))
                command_center.set_topology(topo_path)

            self._send_json_response({
                "status": "success",
                "message": "Configuración actualizada correctamente",
                "current_state": command_center.get_current_state()
            })
            return

        elif parsed.path == "/api/simulation/start":
            started = command_center.start_simulation_thread(step_delay=0.5)
            self._send_json_response({
                "status": "success" if started else "already_running",
                "is_running": command_center.is_simulation_active()
            })
            return

        elif parsed.path == "/api/simulation/stop":
            command_center.stop_simulation()
            self._send_json_response({
                "status": "success",
                "is_running": False
            })
            return

        elif parsed.path == "/api/deploy":
            out_manifest = command_center.deploy_containers()
            self._send_json_response({
                "status": "success",
                "manifest": out_manifest,
                "message": f"Manifiesto {out_manifest} generado con 8 contenedores aislados."
            })
            return

        self._send_json_response({"error": "Endpoint no encontrado"}, 404)

class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

def start_server(start_port=8000, open_browser=True):
    os.chdir(DIRECTORY)
    candidate_ports = [8000, 8080, 8888, 5000, 9000, 8081, 8082, 8085]
    if start_port not in candidate_ports:
        candidate_ports.insert(0, start_port)

    for port in candidate_ports:
        try:
            httpd = ReusableTCPServer(("127.0.0.1", port), APIAndStaticHandler)
            url = f"http://127.0.0.1:{port}/web_dashboard.html"
            print("=======================================================")
            print("  Servidor Web & API REST del Centro de Mando Activo en:")
            print(f"  URL: {url}")
            print("=======================================================")
            if open_browser:
                try:
                    webbrowser.open(url)
                except Exception:
                    pass

            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("Servidor web finalizado por el usuario.")
            return httpd
        except (OSError, PermissionError):
            continue

    print("Error: No se pudo abrir un puerto libre en 127.0.0.1.")
    return None

if __name__ == "__main__":
    start_port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    start_server(start_port)

