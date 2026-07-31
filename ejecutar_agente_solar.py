"""Script de ejecucion de un agente Solar remoto via ZeroMQ.

Uso:
  python ejecutar_agente_solar.py --id 2 --host 192.168.1.6 --puerto 5555

El agente se conecta a la PC Central, recibe ticks y reporta
la generacion solar segun un perfil sintetico (campana gaussiana).
La dinamica solar puede ser local (embebida) o remota (servicio externo).
"""

import argparse
import time

from MAS.agente_zmq import AgenteZMQ
from Solar.SolarSimplificado import SolarSimplificado


def ejecutar_solar_local(id_agente, host, puerto, P_rated, paso_maestro):
    solar = SolarSimplificado(P_rated=P_rated, T_total=3600.0)
    _loop_solar(id_agente, host, puerto, paso_maestro, solar)


def ejecutar_solar_remoto(id_agente, host, puerto, P_rated,
                           paso_maestro, dinamica_host, dinamica_puerto):
    from MAS.cliente_dinamica import ClienteDinamica
    dinamica = ClienteDinamica(host=dinamica_host, puerto=dinamica_puerto)
    dinamica.conectar()

    class SolarProxy:
        def __init__(self, cli, P_rated):
            self._cli = cli
            self.P_rated = P_rated
            self.SoC = 0.0
            self.P_ref = 0.0
            self.P_real = 0.0

        def step(self, dt, P_ref, V_pcc=None):
            resp = self._cli.step(dt, P_ref, V_pcc=V_pcc)
            self.SoC = resp.get("SoC", 0.0)
            self.P_ref = resp.get("P_ref", 0.0)
            self.P_real = resp.get("P_real", 0.0)

    solar = SolarProxy(dinamica, P_rated)
    _loop_solar(id_agente, host, puerto, paso_maestro, solar)
    dinamica.desconectar()


def _loop_solar(id_agente, host, puerto, paso_maestro, modelo):
    zmq = AgenteZMQ(id_agente, host=host, puerto=puerto, timeout_ms=15000)
    conectado = False
    for intento in range(30):
        try:
            zmq.conectar()
            conectado = True
            break
        except (ConnectionRefusedError, TimeoutError, OSError) as e:
            if intento % 10 == 0:
                print(f"[Solar:{id_agente}] Esperando servidor... "
                      f"({e})")
            import time as _time
            _time.sleep(2)
    if not conectado:
        print(f"[Solar:{id_agente}] No se pudo conectar al servidor")
        return

    print(f"[Solar:{id_agente}] Iniciando loop. P_rated={modelo.P_rated:.0f}W")

    try:
        while True:
            tick = zmq.esperar_tick()
            if tick is None:
                break

            paso = tick.get("step", 0)
            V_pcc_dict = tick.get("V_pcc", {})

            V_pcc_ag = V_pcc_dict.get(str(id_agente))
            modelo.step(paso_maestro, 0.0, V_pcc=V_pcc_ag)

            zmq.enviar_medicion(
                P_ref=modelo.P_real,
                SoC=modelo.SoC,
                cobertura=1,
                SoC_avg=0.0,
                paso=paso,
            )

            if paso % 500 == 0:
                print(f"  [Solar:{id_agente}] paso {paso} "
                      f"P={modelo.P_real:.0f}W SoC={modelo.SoC:.4f}")

    except KeyboardInterrupt:
        print(f"[Solar:{id_agente}] Interrupcion del usuario")

    zmq.desconectar()
    print(f"[Solar:{id_agente}] Finalizado")


def main():
    parser = argparse.ArgumentParser(
        description="Agente Solar para co-simulacion MAS"
    )
    parser.add_argument("--id", type=int, default=2)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--puerto", type=int, default=5555)
    parser.add_argument("--P_rated", type=float, default=3000.0)
    parser.add_argument("--paso", type=float, default=0.1)
    parser.add_argument("--modo", choices=["local", "remoto"], default="local")
    parser.add_argument("--dinamica-host", default="127.0.0.1")
    parser.add_argument("--dinamica-puerto", type=int, default=6000)
    args = parser.parse_args()

    if args.modo == "local":
        ejecutar_solar_local(
            id_agente=args.id,
            host=args.host,
            puerto=args.puerto,
            P_rated=args.P_rated,
            paso_maestro=args.paso,
        )
    else:
        ejecutar_solar_remoto(
            id_agente=args.id,
            host=args.host,
            puerto=args.puerto,
            P_rated=args.P_rated,
            paso_maestro=args.paso,
            dinamica_host=args.dinamica_host,
            dinamica_puerto=args.dinamica_puerto,
        )


if __name__ == "__main__":
    main()
