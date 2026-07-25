import json
import select
import socket
import time
from typing import Any, Dict, List, Optional, Tuple


class RelojZMQ:
    """Servidor maestro que coordina agentes via TCP."""

    def __init__(self, puerto: int = 5555, paso_maestro: float = 0.1,
                 timeout_ms: int = 5000) -> None:
        self.puerto: int = puerto
        self.paso_maestro: float = paso_maestro
        self.timeout: float = timeout_ms / 1000.0
        self._server: Optional[socket.socket] = None
        self._agentes: Dict[Tuple, Dict[str, Any]] = {}
        self._buffer_in: bytes = b""

    def iniciar(self) -> None:
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("0.0.0.0", self.puerto))
        self._server.listen(10)
        self._server.setblocking(False)
        print(f"[RelojZMQ] Servidor en puerto {self.puerto}")

    def esperar_agentes(self, n: int, timeout: float = 10.0) -> int:
        t0 = time.time()
        while len(self._agentes) < n and (time.time() - t0) < timeout:
            self._aceptar_conexiones()
            time.sleep(0.05)
        conectados = len(self._agentes)
        if conectados < n:
            print(f"[RelojZMQ] ADVERTENCIA: solo "
                  f"{conectados}/{n} agentes conectados")
        else:
            print(f"[RelojZMQ] {conectados}/{n} agentes conectados")
        return conectados

    def _aceptar_conexiones(self) -> None:
        if self._server is None:
            return
        try:
            while True:
                client, addr = self._server.accept()
                client.setblocking(False)
                buf: bytes = b""
                self._agentes[addr] = {"socket": client, "buf": buf,
                                       "id": None}
                print(f"[RelojZMQ] Conexion de {addr}")
        except BlockingIOError:
            pass

    def _leer_mensajes(self) -> List[Tuple[Tuple, Dict[str, Any]]]:
        mensajes: List[Tuple[Tuple, Dict[str, Any]]] = []
        desconectados: List[Tuple] = []
        for addr, info in list(self._agentes.items()):
            sock = info["socket"]
            buf: bytes = info["buf"]
            try:
                datos = sock.recv(4096)
                if not datos:
                    desconectados.append(addr)
                    continue
                buf += datos
                while b"\n" in buf:
                    linea, buf = buf.split(b"\n", 1)
                    if linea.strip():
                        try:
                            msg = json.loads(linea.decode("utf-8"))
                            mensajes.append((addr, msg))
                        except json.JSONDecodeError:
                            print(f"[RelojZMQ] Mensaje malformado "
                                  f"de {addr}: {linea}")
                info["buf"] = buf
            except BlockingIOError:
                pass
            except ConnectionResetError:
                desconectados.append(addr)

        for addr in desconectados:
            print(f"[RelojZMQ] Desconexion de {addr}")
            self._agentes[addr]["socket"].close()
            del self._agentes[addr]

        return mensajes

    def _procesar_hello(self, addr: Tuple, msg: Dict[str, Any]) -> None:
        ag_id = msg.get("id")
        if ag_id is not None and addr in self._agentes:
            self._agentes[addr]["id"] = ag_id
            print(f"[RelojZMQ] Agente {ag_id} registrado desde {addr}")

    def enviar_tick(self, step: int, tiempo: float,
                    V_pcc: Dict[str, float], demanda_w: float,
                    datos_adicionales: Optional[Dict[str, Any]] = None
                    ) -> None:
        msg: Dict[str, Any] = {
            "tipo": "tick",
            "step": step,
            "tiempo": round(tiempo, 3),
            "V_pcc": V_pcc,
            "demanda_w": demanda_w,
        }
        if datos_adicionales:
            msg.update(datos_adicionales)
        payload = (json.dumps(msg) + "\n").encode("utf-8")

        desconectados: List[Tuple] = []
        for addr, info in list(self._agentes.items()):
            try:
                info["socket"].sendall(payload)
            except (BrokenPipeError, ConnectionResetError):
                desconectados.append(addr)

        for addr in desconectados:
            self._agentes[addr]["socket"].close()
            del self._agentes[addr]

    def recibir_mediciones(self, n_agentes: int
                           ) -> Dict[int, Dict[str, Any]]:
        mediciones: Dict[int, Dict[str, Any]] = {}
        t0 = time.time()

        while (len(mediciones) < n_agentes
               and (time.time() - t0) < self.timeout):
            self._aceptar_conexiones()
            for addr, msg in self._leer_mensajes():
                if msg.get("tipo") == "hello":
                    self._procesar_hello(addr, msg)
                elif msg.get("tipo") == "medicion":
                    ag_id = msg.get("id")
                    if ag_id is not None:
                        mediciones[ag_id] = msg

        if len(mediciones) < n_agentes:
            recibidos = list(mediciones.keys())
            print(f"[RelojZMQ] Solo {len(mediciones)}/{n_agentes} "
                  f"mediciones: {recibidos}")

        return mediciones

    def detener(self) -> None:
        for addr, info in list(self._agentes.items()):
            try:
                info["socket"].close()
            except OSError:
                pass
        self._agentes.clear()
        if self._server:
            self._server.close()
            self._server = None
        print("[RelojZMQ] Servidor detenido")
