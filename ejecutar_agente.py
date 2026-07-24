"""Script de ejecucion de un agente BESS remoto via ZeroMQ.

Uso:
  python ejecutar_agente.py --id 1 --host 127.0.0.1 --puerto 5555
      --SoC 0.8 --P_rated 20000 --K_soc 2.0

Cada agente se conecta al RelojZMQ de la PC Central y participa
en la co-simulacion distribuida.
"""

import argparse
import time

from MAS.AgenteConsenso import AgenteConsenso
from MAS.BESS_simplificado import BateriaSimplificada
from MAS.agente_zmq import AgenteZMQ


def ejecutar_agente(id_agente, host, puerto, SoC_inicial, capacidad_Ah,
                     P_rated, K_soc, paso_maestro):
    bess = BateriaSimplificada(
        V_nominal=48.0, capacidad_Ah=capacidad_Ah,
        SoC_inicial=SoC_inicial, N_serie=10
    )

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
            SoC_avg = tick.get("SoC_avg", bess.SoC)
            paso = tick.get("step", 0)

            num_agentes = tick.get("num_agentes", 1)
            fraccion = 1.0 / num_agentes if num_agentes > 0 else 1.0
            desvio = bess.SoC - SoC_avg
            fraccion += K_soc * desvio
            P_ref = demanda_w * fraccion
            P_ref = max(-P_rated, min(P_rated, P_ref))

            bess.step(paso_maestro, P_ref)

            zmq.enviar_medicion(
                P_ref=P_ref,
                SoC=bess.SoC,
                cobertura=1,
                SoC_avg=SoC_avg,
                paso=paso,
            )

            if paso % 500 == 0:
                print(f"  [Ag:{id_agente}] paso {paso} "
                      f"SoC={bess.SoC:.4f} P_ref={P_ref:.0f}W")

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
    args = parser.parse_args()

    ejecutar_agente(
        id_agente=args.id,
        host=args.host,
        puerto=args.puerto,
        SoC_inicial=args.SoC,
        capacidad_Ah=args.capacidad_Ah,
        P_rated=args.P_rated,
        K_soc=args.K_soc,
        paso_maestro=args.paso,
    )


if __name__ == "__main__":
    main()
