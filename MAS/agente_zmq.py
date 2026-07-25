"""Cliente ZeroMQ para agente MAS.

Se conecta al RelojZMQ de la PC Central, recibe ticks y envia mediciones.
Usa sockets TCP stdlib con mensajes JSON terminados en '\\n'.
"""

import json
import socket
from typing import Any, Dict, Optional


class AgenteZMQ:
    """Cliente TCP para comunicacion con la PC Central."""

    def __init__(self, id_agente: int, host: str = "127.0.0.1",
                 puerto: int = 5555, timeout_ms: int = 5000) -> None:
        self.id: int = id_agente
        self.host: str = host
        self.puerto: int = puerto
        self.timeout: float = timeout_ms / 1000.0
        self._socket: Optional[socket.socket] = None
        self._buf: bytes = b""

    def conectar(self) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(self.timeout)
        self._socket.connect((self.host, self.puerto))
        self._socket.setblocking(False)
        self._enviar({"tipo": "hello", "id": self.id})
        print(f"[AgenteZMQ:{self.id}] Conectado a {self.host}:{self.puerto}")

    def _enviar(self, msg_dict: Dict[str, Any]) -> None:
        if self._socket is None:
            return
        payload = (json.dumps(msg_dict) + "\n").encode("utf-8")
        try:
            self._socket.sendall(payload)
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            print(f"[AgenteZMQ:{self.id}] Error al enviar: {e}")

    def _leer_mensaje(self) -> Optional[Dict[str, Any]]:
        if self._socket is None:
            return None
        try:
            datos = self._socket.recv(4096)
            if not datos:
                print(f"[AgenteZMQ:{self.id}] Servidor desconectado")
                return "_DESCONECTADO_"
            self._buf += datos
            if b"\n" in self._buf:
                linea, self._buf = self._buf.split(b"\n", 1)
                if linea.strip():
                    return json.loads(linea.decode("utf-8"))
        except BlockingIOError:
            pass
        except (ConnectionResetError, OSError) as e:
            print(f"[AgenteZMQ:{self.id}] Error de conexion: {e}")
            return "_DESCONECTADO_"
        return None

    def esperar_tick(self) -> Optional[Dict[str, Any]]:
        import select as _select
        import time as _time

        t0 = _time.time()
        while (_time.time() - t0) < self.timeout:
            msg = self._leer_mensaje()
            if msg == "_DESCONECTADO_":
                return None
            if msg is not None and msg.get("tipo") == "tick":
                return msg
            _time.sleep(0.001)

        print(f"[AgenteZMQ:{self.id}] Timeout esperando tick")
        return None

    def enviar_medicion(self, P_ref: float, SoC: float,
                        cobertura: int, SoC_avg: float,
                        **extra: Any) -> None:
        msg: Dict[str, Any] = {
            "tipo": "medicion",
            "id": self.id,
            "P_ref": round(P_ref, 1),
            "SoC": round(SoC, 6),
            "cobertura": cobertura,
            "SoC_avg": round(SoC_avg, 6),
        }
        msg.update(extra)
        self._enviar(msg)

    def desconectar(self) -> None:
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        print(f"[AgenteZMQ:{self.id}] Desconectado")
