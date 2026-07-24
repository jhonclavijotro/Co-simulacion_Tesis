"""Reloj maestro con comunicacion distribuida via TCP/sockets (stdlib).

Implementa un patron PUB/PULL sobre TCP plano con mensajes JSON.
La PC Central actua como servidor: los agentes se conectan,
reciben ticks y envian mediciones.

Protocolo:
  - Cada mensaje es una linea JSON terminada en '\\n'
  - Handshake: agente envia {"tipo":"hello","id":N}
  - Tick: servidor envia {"tipo":"tick","step":N,"tiempo":T,"V_pcc":{...},"demanda_w":W}
  - Medicion: agente responde {"tipo":"medicion","id":N,"P_ref":P,"SoC":S,...}
"""

import json
import select
import socket
import time


class RelojZMQ:
    """Servidor maestro que coordina agentes via TCP.

    Patron de comunicacion:
      PUB (broadcast) — envia ticks a todos los agentes conectados
      PULL (collect)  — recibe mediciones de todos los agentes
    """

    def __init__(self, puerto=5555, paso_maestro=0.1, timeout_ms=5000):
        self.puerto = puerto
        self.paso_maestro = paso_maestro
        self.timeout = timeout_ms / 1000.0
        self._server = None
        self._agentes = {}
        self._buffer_in = b""

    def iniciar(self):
        """Crea socket servidor TCP y escucha en el puerto."""
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("0.0.0.0", self.puerto))
        self._server.listen(10)
        self._server.setblocking(False)
        print(f"[RelojZMQ] Servidor en puerto {self.puerto}")

    def esperar_agentes(self, n, timeout=10.0):
        """Espera hasta que N agentes se conecten."""
        t0 = time.time()
        while len(self._agentes) < n and (time.time() - t0) < timeout:
            self._aceptar_conexiones()
            time.sleep(0.05)
        conectados = len(self._agentes)
        if conectados < n:
            print(f"[RelojZMQ] ADVERTENCIA: solo {conectados}/{n} agentes conectados")
        else:
            print(f"[RelojZMQ] {conectados}/{n} agentes conectados")
        return conectados

    def _aceptar_conexiones(self):
        """Acepta nuevas conexiones entrantes (non-blocking)."""
        if self._server is None:
            return
        try:
            while True:
                client, addr = self._server.accept()
                client.setblocking(False)
                buf = b""
                self._agentes[addr] = {"socket": client, "buf": buf, "id": None}
                print(f"[RelojZMQ] Conexion de {addr}")
        except BlockingIOError:
            pass

    def _leer_mensajes(self):
        """Lee datos de todos los sockets de agentes, extrae mensajes JSON."""
        mensajes = []
        desconectados = []
        for addr, info in list(self._agentes.items()):
            sock = info["socket"]
            buf = info["buf"]
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
                            print(f"[RelojZMQ] Mensaje malformado de {addr}: {linea}")
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

    def _procesar_hello(self, addr, msg):
        """Procesa mensaje HELLO de un agente."""
        ag_id = msg.get("id")
        if ag_id is not None and addr in self._agentes:
            self._agentes[addr]["id"] = ag_id
            print(f"[RelojZMQ] Agente {ag_id} registrado desde {addr}")

    def enviar_tick(self, step, tiempo, V_pcc, demanda_w, datos_adicionales=None):
        """Broadcast TICK a todos los agentes conectados."""
        msg = {
            "tipo": "tick",
            "step": step,
            "tiempo": round(tiempo, 3),
            "V_pcc": V_pcc,
            "demanda_w": demanda_w,
        }
        if datos_adicionales:
            msg.update(datos_adicionales)
        payload = (json.dumps(msg) + "\n").encode("utf-8")

        desconectados = []
        for addr, info in list(self._agentes.items()):
            try:
                info["socket"].sendall(payload)
            except (BrokenPipeError, ConnectionResetError):
                desconectados.append(addr)

        for addr in desconectados:
            self._agentes[addr]["socket"].close()
            del self._agentes[addr]

    def recibir_mediciones(self, n_agentes):
        """Espera y retorna mediciones de todos los agentes.

        Retorna:
            dict {id_agente: mensaje_json} con las mediciones recibidas.
        """
        mediciones = {}
        t0 = time.time()

        while len(mediciones) < n_agentes and (time.time() - t0) < self.timeout:
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
            print(f"[RelojZMQ] Solo {len(mediciones)}/{n_agentes} mediciones: {recibidos}")

        return mediciones

    def detener(self):
        """Cierra todas las conexiones."""
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
