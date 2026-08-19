import http.server
import socketserver
import os
import webbrowser
import sys

DIRECTORY = os.path.dirname(os.path.abspath(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

def start_server(start_port=8000):
    os.chdir(DIRECTORY)
    candidate_ports = [8000, 8080, 8888, 5000, 9000, 8081, 8082, 8085]
    if start_port not in candidate_ports:
        candidate_ports.insert(0, start_port)

    for port in candidate_ports:
        try:
            # Enlazar a '127.0.0.1' evita restricciones de Firewall/Hyper-V en Windows (WinError 10013)
            httpd = ReusableTCPServer(("127.0.0.1", port), Handler)
            url = f"http://127.0.0.1:{port}/web_dashboard.html"
            print("=======================================================")
            print("  Servidor Web del Centro de Mando Activo en:")
            print(f"  URL: {url}")
            print("=======================================================")
            try:
                webbrowser.open(url)
            except Exception:
                pass

            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("Servidor web finalizado por el usuario.")
            return
        except (OSError, PermissionError):
            # Continuar intentando con el siguiente puerto si el actual está ocupado u reservado
            continue

    print("Error: No se pudo abrir un puerto libre en 127.0.0.1.")

if __name__ == "__main__":
    start_port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    start_server(start_port)
