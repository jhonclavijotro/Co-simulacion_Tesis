#!/usr/bin/env python3
"""Servidor PC Central para ejecucion en Docker.

Inicia el RelojZMQ, espera N agentes, y ejecuta la co-simulacion.
Uso: python server_pc.py [N] [puerto] [demanda_w] [tiempo_total]
"""

import sys, json, time
sys.path.insert(0, ".")

from CentralPC.reloj_zmq import RelojZMQ
from CentralPC.master_clock import MasterClock


def main() -> None:
    N: int = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    puerto: int = int(sys.argv[2]) if len(sys.argv) > 2 else 5555
    demanda: float = float(sys.argv[3]) if len(sys.argv) > 3 else 15000.0
    tiempo_total: float = float(sys.argv[4]) if len(sys.argv) > 4 else 60.0

    print(f"PC Central iniciando... N={N} puerto={puerto}")
    r = RelojZMQ(puerto=puerto, paso_maestro=0.1)
    r.iniciar()

    n_conectados = r.esperar_agentes(N, timeout=120.0)
    if n_conectados < N:
        print(f"ADVERTENCIA: solo {n_conectados}/{N} agentes conectados")

    mc = MasterClock(paso_maestro=0.1)
    tiempo = 0.0
    paso = 0
    SoCs = {i: 0.5 for i in range(1, N + 1)}

    while tiempo < tiempo_total:
        avg = sum(SoCs.values()) / N
        SoC_avg = round(avg, 6)
        extras = {
            "SoC_avg": SoC_avg,
            "SoCs": {str(k): round(v, 6) for k, v in SoCs.items()},
        }
        r.enviar_tick(paso, tiempo, {}, demanda, extras)
        ms = r.recibir_mediciones(N)

        for k, v in ms.items():
            SoCs[k] = v.get("SoC", SoCs[k])

        mc.step()
        tiempo = mc.tiempo
        paso += 1

        if paso % 100 == 0:
            print(f"paso {paso} t={tiempo:.1f}s SoC_avg={SoC_avg:.4f}")

    r.detener()
    print(f"PC Central finalizado: {paso} pasos en {tiempo_total:.1f}s")


if __name__ == "__main__":
    main()
