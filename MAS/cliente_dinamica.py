"""Cliente TCP para conectarse al servicio de dinamica remoto.

Usa el mismo patron JSON+'\\n' que agente_zmq.py.
"""

import json
import socket
from typing import Any, Dict, Optional


class ClienteDinamica:
    """Cliente para ServicioDinamica remoto."""

    def __init__(self, host: str = "127.0.0.1", puerto: int = 6000,
                 timeout: float = 5.0) -> None:
        self.host: str = host
        self.puerto: int = puerto
        self.timeout: float = timeout
        self._socket: Optional[socket.socket] = None
        self._buf: bytes = b""

    def conectar(self) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(self.timeout)
        self._socket.connect((self.host, self.puerto))
        self._socket.setblocking(False)
        print(f"[ClienteDinamica] Conectado a {self.host}:{self.puerto}")

    def _enviar(self, msg_dict: Dict[str, Any]) -> None:
        if self._socket is None:
            return
        payload = (json.dumps(msg_dict) + "\n").encode("utf-8")
        try:
            self._socket.sendall(payload)
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            print(f"[ClienteDinamica] Error envio: {e}")

    def _leer_respuesta(self, max_espera: float = 5.0
                         ) -> Optional[Dict[str, Any]]:
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

    def step(self, dt: float, P_ref: float,
             V_pcc: Optional[float] = None) -> Dict[str, Any]:
        msg: Dict[str, Any] = {"comando": "step", "dt": dt, "P_ref": P_ref}
        if V_pcc is not None:
            msg["V_pcc"] = V_pcc
        self._enviar(msg)
        resp = self._leer_respuesta()
        if resp is None:
            raise ConnectionError("Sin respuesta del servicio de dinamica")
        if not resp.get("ok"):
            raise RuntimeError(resp.get("error", "Error desconocido"))
        return resp

    def set_param(self, **params) -> Dict[str, Any]:
        self._enviar({"comando": "set_param", "params": params})
        resp = self._leer_respuesta()
        if resp is None:
            raise ConnectionError("Sin respuesta del servicio de dinamica")
        return resp

    def estado(self) -> Dict[str, Any]:
        self._enviar({"comando": "estado"})
        resp = self._leer_respuesta()
        if resp is None:
            raise ConnectionError("Sin respuesta del servicio de dinamica")
        return resp

    def desconectar(self) -> None:
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        print("[ClienteDinamica] Desconectado")
