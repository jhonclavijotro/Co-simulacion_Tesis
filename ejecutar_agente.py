"""Script de ejecucion de un agente BESS remoto via ZeroMQ.

Uso local (dinamica embebida):
  python ejecutar_agente.py --id 1 --host 127.0.0.1 --puerto 5555
      --SoC 0.8 --P_rated 20000 --K_soc 2.0

Uso Docker (dinamica remota):
  python ejecutar_agente.py --id 1 --host pc-central --puerto 5555
      --SoC 0.8 --P_rated 20000 --K_soc 2.0 --modo remoto
      --dinamica-host dinamica-1 --dinamica-puerto 6000
"""

import argparse
import time

from MAS.AgenteConsenso import AgenteConsenso
from MAS.BESS_simplificado import BateriaSimplificada
from MAS.agente_zmq import AgenteZMQ


def ejecutar_agente_local(id_agente, host, puerto, SoC_inicial, capacidad_Ah,
                           P_rated, K_soc, paso_maestro):
    bess = BateriaSimplificada(
        V_nominal=48.0, capacidad_Ah=capacidad_Ah,
        SoC_inicial=SoC_inicial, N_serie=10
    )
    _loop_agente(id_agente, host, puerto, SoC_inicial, P_rated, K_soc,
                 paso_maestro, bess)


def ejecutar_agente_remoto(id_agente, host, puerto, P_rated, K_soc,
                            paso_maestro, dinamica_host, dinamica_puerto):
    from MAS.cliente_dinamica import ClienteDinamica
    dinamica = ClienteDinamica(host=dinamica_host, puerto=dinamica_puerto)
    dinamica.conectar()
    estado = dinamica.estado()
    SoC_inicial = estado.get("SoC", 0.5)

    class BESSProxy:
        def __init__(self, cli):
            self._cli = cli
            self.SoC = SoC_inicial
            self.P_ref = 0.0
            self.P_real = 0.0

        def step(self, dt, P_ref):
            resp = self._cli.step(dt, P_ref)
            self.SoC = resp["SoC"]
            self.P_ref = resp["P_ref"]
            self.P_real = resp["P_real"]

    bess = BESSProxy(dinamica)
    _loop_agente(id_agente, host, puerto, SoC_inicial, P_rated, K_soc,
                 paso_maestro, bess)
    dinamica.desconectar()


def _loop_agente(id_agente, host, puerto, SoC_inicial,
                  P_rated, K_soc, paso_maestro, modelo):
    consenso = AgenteConsenso(id_agente, [], 1)
    consenso.init_tabla(SoC_inicial)

    zmq = AgenteZMQ(id_agente, host=host, puerto=puerto)
    zmq.conectar()

    print(f"[Agente:{id_agente}] Iniciando loop. "
          f"SoC={SoC_inicial:.4f}, P_rated={P_rated:.0f}W")

    try:
        while True:
            tick = zmq.esperar_tick()
            if tick is None:
                break

            demanda_w = tick.get("demanda_w", 0)
            SoC_avg = tick.get("SoC_avg", modelo.SoC)
            paso = tick.get("step", 0)

            num_agentes = tick.get("num_agentes", 1)
            fraccion = 1.0 / num_agentes if num_agentes > 0 else 1.0
            desvio = modelo.SoC - SoC_avg
            fraccion += K_soc * desvio
            P_ref = demanda_w * fraccion
            P_ref = max(-P_rated, min(P_rated, P_ref))

            modelo.step(paso_maestro, P_ref)

            zmq.enviar_medicion(
                P_ref=P_ref,
                SoC=modelo.SoC,
                cobertura=1,
                SoC_avg=SoC_avg,
                paso=paso,
            )

            if paso % 500 == 0:
                print(f"  [Ag:{id_agente}] paso {paso} "
                      f"SoC={modelo.SoC:.4f} P_ref={P_ref:.0f}W")

    except KeyboardInterrupt:
        print(f"[Agente:{id_agente}] Interrupcion del usuario")

    zmq.desconectar()
    print(f"[Agente:{id_agente}] Finalizado")


def main():
    parser = argparse.ArgumentParser(
        description="Agente BESS remoto para co-simulacion MAS"
    )
    parser.add_argument("--id", type=int, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--puerto", type=int, default=5555)
    parser.add_argument("--SoC", type=float, default=0.5)
    parser.add_argument("--capacidad_Ah", type=float, default=5.0)
    parser.add_argument("--P_rated", type=float, default=20000.0)
    parser.add_argument("--K_soc", type=float, default=2.0)
    parser.add_argument("--paso", type=float, default=0.1)
    parser.add_argument("--modo", choices=["local", "remoto"], default="local")
    parser.add_argument("--dinamica-host", default="127.0.0.1")
    parser.add_argument("--dinamica-puerto", type=int, default=6000)
    args = parser.parse_args()

    if args.modo == "local":
        ejecutar_agente_local(
            id_agente=args.id,
            host=args.host,
            puerto=args.puerto,
            SoC_inicial=args.SoC,
            capacidad_Ah=args.capacidad_Ah,
            P_rated=args.P_rated,
            K_soc=args.K_soc,
            paso_maestro=args.paso,
        )
    else:
        ejecutar_agente_remoto(
            id_agente=args.id,
            host=args.host,
            puerto=args.puerto,
            P_rated=args.P_rated,
            K_soc=args.K_soc,
            paso_maestro=args.paso,
            dinamica_host=args.dinamica_host,
            dinamica_puerto=args.dinamica_puerto,
        )


if __name__ == "__main__":
    main()
