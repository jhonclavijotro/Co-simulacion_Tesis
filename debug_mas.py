import sys
sys.path.insert(0, '.')
from MAS.CoordinadorMAS import CoordinadorMAS

config = [
    {"id": 1, "vecinos": [2],    "SoC_inicial": 0.8, "P_rated": 10000, "K_soc": 1.0},
    {"id": 2, "vecinos": [1, 3], "SoC_inicial": 0.5, "P_rated": 10000, "K_soc": 1.0},
    {"id": 3, "vecinos": [2],    "SoC_inicial": 0.3, "P_rated": 10000, "K_soc": 1.0},
]

coord = CoordinadorMAS(config, paso_maestro=1.0)
coord.pc.registrar_inyeccion(0, 0.0, 0.0)
coord.pc.registrar_inyeccion(3, -15000.0, 0.0)

coord.tiempo = 0.0
for i in range(3):
    print(f"=== Paso {i} ===")
    for ag in coord.agentes.values():
        estados = {}
        for vid in ag.consenso.vecinos:
            if vid in coord.agentes:
                estados[vid] = coord.agentes[vid].SoC
        print(f"  Ag{ag.id}: SoC={ag.SoC:.4f}, SoC_avg_before={ag.SoC_avg:.4f}")
        ag.paso_consenso(estados)
        print(f"    -> SoC_avg_after={ag.SoC_avg:.4f}")

    P_total = coord._total_demanda()
    print(f"P_total={P_total:.0f}W")

    for ag in coord.agentes.values():
        ag.calcular_P_ref(P_total)
        coord.pc.registrar_inyeccion(ag.id, ag.P_ref, 0.0)
        V_bat = ag.bess.contexto["V_bat"]
        I_bat = ag.bess.contexto["I_bat"]
        print(f"  Ag{ag.id}: P_ref={ag.P_ref:.0f}W, V_bat={V_bat:.1f}V, I_bat={I_bat:.1f}A")

    coord.V = coord.pc.step()
    print(f"  Tensions: { {n: f'{abs(coord.V[n]):.4f}' for n in coord.pc.nodos_red} }")

    for ag in coord.agentes.values():
        V_pu = abs(coord.V.get(ag.id, complex(1.0, 0)))
        V_pcc = V_pu * 110.0
        ag.step(coord.paso_maestro, V_pcc, P_total)
        ctx = ag.bess.contexto
        ag.registrar_historico(coord.tiempo)
        print(f"  Ag{ag.id} step: SoC={ag.SoC:.4f}, V_bat={ctx['V_bat']:.1f}V, "
              f"I_bat={ctx['I_bat']:.1f}A, P_bat={ctx['P_bat']:.0f}W")

    coord.tiempo = coord.pc.tiempo
    print(f"t={coord.tiempo:.1f}s\n")
