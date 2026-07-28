"""Servicio de dinamica generico para fuentes de generacion.

Expone el modelo fisico via TCP/JSON para que el agente de consenso
se conecte de forma remota (separacion estricta de procesos).

Protocolo (JSON + '\\n'):
  Request:
    {"comando": "step", "dt": 0.1, "P_ref": 5000.0}
    {"comando": "estado"}
  Response:
    {"ok": true, "SoC": 0.75, "V_pack": 480.0, ...}
"""

import json
import socket
import sys
import time

sys.path.insert(0, ".")

from Diesel.SistemaDiesel import SistemaDiesel
from Hidrica.SistemaHidrico import SistemaHidrico
from MAS.BESS_simplificado import BateriaSimplificada


_FABRICA = {
    "BESS": lambda p: BateriaSimplificada(
        V_nominal=p.get("V_nominal", 48.0),
        capacidad_Ah=p.get("capacidad_Ah", 200.0),
        SoC_inicial=p.get("SoC", 0.5),
        N_serie=p.get("N_serie", 10),
    ),
    "Hidrica": lambda p: SistemaHidrico(
        R=p.get("R", 1.5),
        B=p.get("B", 0.0),
        relacion=p.get("relacion", 4.0),
        eta=p.get("eta", 0.95),
    ),
    "Diesel": lambda p: SistemaDiesel(
        Kp_gov=p.get("Kp_gov", 0.001),
        Ki_gov=p.get("Ki_gov", 0.02),
        eta=p.get("eta", 0.95),
    ),
}


class ServicioDinamica:
    """Servidor TCP que envuelve un modelo de dinamica y expone step()."""

    def __init__(self, fuente, params, host="0.0.0.0", puerto=6000):
        self.fuente = fuente
        self.params = params
        self.host = host
        self.puerto = puerto
        self._crear_modelo()
        self._server = None

    def _crear_modelo(self):
        crear = _FABRICA.get(self.fuente)
        if crear is None:
            raise ValueError(
                f"Fuente desconocida: {self.fuente}. "
                f"Disponibles: {list(_FABRICA.keys())}"
            )
        self.modelo = crear(self.params)
        print(f"[ServicioDinamica] {self.fuente} creado: "
              f"SoC={self.modelo.SoC:.4f}")

    def _handle(self, msg):
        cmd = msg.get("comando", "")
        if cmd == "step":
            dt = msg.get("dt", 0.1)
            P_ref = msg.get("P_ref", 0.0)
            self.modelo.step(dt, P_ref)
            return {"ok": True, "SoC": self.modelo.SoC,
                    "P_ref": self.modelo.P_ref, "P_real": self.modelo.P_real}
        elif cmd == "estado":
            return {"ok": True, "fuente": self.fuente,
                    "SoC": self.modelo.SoC, "P_ref": self.modelo.P_ref,
                    "P_real": self.modelo.P_real}
        else:
            return {"ok": False, "error": f"Comando desconocido: {cmd}"}

    def iniciar(self):
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self.host, self.puerto))
        self._server.listen(1)
        self._server.settimeout(1.0)
        print(f"[ServicioDinamica] Escuchando en {self.host}:{self.puerto} "
              f"(fuente={self.fuente})")
        try:
            while True:
                try:
                    conn, addr = self._server.accept()
                except socket.timeout:
                    continue
                print(f"[ServicioDinamica] Conectado: {addr}")
                with conn:
                    conn.settimeout(5.0)
                    buf = b""
                    try:
                        while True:
                            datos = conn.recv(4096)
                            if not datos:
                                break
                            buf += datos
                            while b"\n" in buf:
                                linea, buf = buf.split(b"\n", 1)
                                if not linea.strip():
                                    continue
                                req = json.loads(linea.decode("utf-8"))
                                resp = self._handle(req)
                                conn.sendall(
                                    (json.dumps(resp) + "\n").encode("utf-8")
                                )
                    except (ConnectionResetError, BrokenPipeError):
                        pass
                    except json.JSONDecodeError as e:
                        print(f"[ServicioDinamica] JSON invalido: {e}")
                    print(f"[ServicioDinamica] Cliente desconectado: {addr}")
        except KeyboardInterrupt:
            pass
        finally:
            self.detener()

    def detener(self):
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None
        print("[ServicioDinamica] Detenido")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Servicio de dinamica")
    parser.add_argument("--fuente", required=True, choices=list(_FABRICA.keys()))
    parser.add_argument("--SoC", type=float, default=0.5)
    parser.add_argument("--P_rated", type=float, default=20000.0)
    parser.add_argument("--capacidad_Ah", type=float, default=200.0)
    parser.add_argument("--puerto", type=int, default=6000)
    args = parser.parse_args()

    svc = ServicioDinamica(
        fuente=args.fuente,
        params={"SoC": args.SoC, "P_rated": args.P_rated,
                "capacidad_Ah": args.capacidad_Ah},
        puerto=args.puerto,
    )
    svc.iniciar()


if __name__ == "__main__":
    main()
