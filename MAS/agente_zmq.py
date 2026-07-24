"""Cliente ZeroMQ para agente MAS.

Se conecta al RelojZMQ de la PC Central, recibe ticks y envia mediciones.
Usa sockets TCP stdlib con mensajes JSON terminados en '\\n'.
"""

import json
import socket


class AgenteZMQ:
    """Cliente TCP para comunicacion con la PC Central.

    Patron:
      SUB — recibe ticks del servidor
      PUSH — envia mediciones al servidor

    Usa UN solo socket bidireccional (TCP full-duplex).
    """

    def __init__(self, id_agente, host="127.0.0.1", puerto=5555,
                 timeout_ms=5000):
        self.id = id_agente
        self.host = host
        self.puerto = puerto
        self.timeout = timeout_ms / 1000.0
        self._socket = None
        self._buf = b""

    def conectar(self):
        """Conecta al servidor y envia HELLO."""
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(self.timeout)
        self._socket.connect((self.host, self.puerto))
        self._socket.setblocking(False)
        self._enviar({"tipo": "hello", "id": self.id})
        print(f"[AgenteZMQ:{self.id}] Conectado a {self.host}:{self.puerto}")

    def _enviar(self, msg_dict):
        """Envia un mensaje JSON por el socket."""
        if self._socket is None:
            return
        payload = (json.dumps(msg_dict) + "\n").encode("utf-8")
        try:
            self._socket.sendall(payload)
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            print(f"[AgenteZMQ:{self.id}] Error al enviar: {e}")

    def _leer_mensaje(self):
        """Lee del socket, extrae el primer mensaje JSON completo.

        Retorna:
            dict con el mensaje, o None si no hay mensaje completo.
        """
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

    def esperar_tick(self):
        """Espera un mensaje TICK del servidor.

        Retorna:
            dict con datos del tick, o None si timeout/desconexion.
        """
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

    def enviar_medicion(self, P_ref, SoC, cobertura, SoC_avg, **extra):
        """Envia medicion al servidor."""
        msg = {
            "tipo": "medicion",
            "id": self.id,
            "P_ref": round(P_ref, 1),
            "SoC": round(SoC, 6),
            "cobertura": cobertura,
            "SoC_avg": round(SoC_avg, 6),
        }
        msg.update(extra)
        self._enviar(msg)

    def desconectar(self):
        """Cierra la conexion."""
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        print(f"[AgenteZMQ:{self.id}] Desconectado")
