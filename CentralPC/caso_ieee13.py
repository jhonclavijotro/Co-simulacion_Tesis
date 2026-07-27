"""Caso de prueba IEEE 13 Nodos — equivalente monofasico.

Uso:
    from CentralPC.caso_ieee13 import CARGAS, MODELOS, V_SLACK
    from CentralPC.solver_sweep import ForwardBackwardSweep
    fbs = ForwardBackwardSweep("CentralPC/red_ieee13.csv")
    V, ok, it = fbs.resolver(CARGAS, MODELOS, V_slack=V_SLACK, tol=1e-6)

Referencia: IEEE 13 Node Test Feeder, 2004.
"""

from math import sqrt as _sqrt

V_SLACK = 1.02

CARGAS = {
    2:  (400000,  290000),  # 634: Y-PQ, 400+j290
    3:  (170000,  125000),  # 645: Y-PQ, 170+j125
    4:  (230000,  132000),  # 646: D-Z,  230+j132
    5:  (1155000, 660000),  # 671: D-PQ, 1155+j660
    7:  (128000,   86000),  # 652: Y-Z,  128+j86
    8:  (170000,   80000),  # 611: Y-I,  170+j80
    11: (843000,  462000),  # 675: Y-PQ, 843+j462
}

DISTRIBUIDA_632_671 = (100000, 58000)

for n in [0, 5]:
    if n not in CARGAS:
        CARGAS[n] = (0, 0)
    p, q = CARGAS[n]
    dp, dq = DISTRIBUIDA_632_671
    CARGAS[n] = (p + dp, q + dq)

CAPACITORES = {
    11: (0, -600000),  # 675: 3×200kVAr wye
    8:  (0, -100000),  # 611: 1×100kVAr fase C
}

for n in CAPACITORES:
    if n in CARGAS:
        p, q = CARGAS[n]
        cp, cq = CAPACITORES[n]
        CARGAS[n] = (p + cp, q + cq)
    else:
        CARGAS[n] = CAPACITORES[n]

MODELOS = {
    2: "PQ",
    3: "PQ",
    4: "Z",
    5: "PQ",
    7: "Z",
    8: "I",
    11: "PQ",
}

BENCHMARK = {
    "P_total_kW": 3577,
    "Q_total_kVAr": 1725,
    "perdidas_kW": 111,
    "V_634_pu": 0.994,
    "V_675_pu": 0.9835,
    "V_671_pu": 0.990,
    "V_652_pu": 0.9825,
}
