"""Cliente TCP para conectarse al servicio de dinamica remoto.

Usa el mismo patron JSON+'\\n' que agente_zmq.py.
"""

import json
import socket


class ClienteDinamica:
    """Cliente para ServicioDinamica remoto."""

    def __init__(self, host="127.0.0.1", puerto=6000, timeout=5.0):
        self.host = host
        self.puerto = puerto
        self.timeout = timeout
        self._socket = None
        self._buf = b""

    def conectar(self):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(self.timeout)
        self._socket.connect((self.host, self.puerto))
        self._socket.setblocking(False)
        print(f"[ClienteDinamica] Conectado a {self.host}:{self.puerto}")

    def _enviar(self, msg_dict):
        if self._socket is None:
            return
        payload = (json.dumps(msg_dict) + "\n").encode("utf-8")
        try:
            self._socket.sendall(payload)
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            print(f"[ClienteDinamica] Error envio: {e}")

    def _leer_respuesta(self, max_espera=5.0):
        import select as _select
        import time as _time
        t0 = _time.time()
        while (_time.time() - t0) < max_espera:
            try:
                datos = self._socket.recv(4096)
                if not datos:
                    return None
                self._buf += datos
                if b"\n" in self._buf:
                    linea, self._buf = self._buf.split(b"\n", 1)
                    return json.loads(linea.decode("utf-8"))
            except BlockingIOError:
                pass
            except (ConnectionResetError, OSError) as e:
                print(f"[ClienteDinamica] Error lectura: {e}")
                return None
            _time.sleep(0.001)
        return None

    def step(self, dt, P_ref):
        self._enviar({"comando": "step", "dt": dt, "P_ref": P_ref})
        resp = self._leer_respuesta()
        if resp is None:
            raise ConnectionError("Sin respuesta del servicio de dinamica")
        if not resp.get("ok"):
            raise RuntimeError(resp.get("error", "Error desconocido"))
        return resp

    def estado(self):
        self._enviar({"comando": "estado"})
        resp = self._leer_respuesta()
        if resp is None:
            raise ConnectionError("Sin respuesta del servicio de dinamica")
        return resp

    def desconectar(self):
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        print("[ClienteDinamica] Desconectado")
