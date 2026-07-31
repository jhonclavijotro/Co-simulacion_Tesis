"""Test del solver FBS con red de 6 nodos.

Topologia radial:
  0 (slack) -- 1 (BESS) -- 2 (L1) -- 3 (Solar) -- 4 (L2) -- 5 (L3)

Inyecciones:
  Slack (0): V=1.0 pu
  BESS  (1): P=+5000W (descarga)
  L1    (2): P=+3000W, Q=+500VAR
  Solar (3): P=-8000W (generacion)
  L2    (4): P=+2000W, Q=+300VAR
  L3    (5): P=+1000W, Q=+200VAR

Uso:
  python Mockdata/test_solver_6nodos.py
"""

import sys; sys.path.insert(0, ".")
from CentralPC.solver_sweep import ForwardBackwardSweep
from CentralPC.master_clock import MasterClock

ARCHIVO_RED = "CentralPC/red_6nodos.csv"


def escenario_1():
    """Escenario base: BESS descarga, Solar genera."""
    print("Escenario 1: BESS descarga (+5kW), Solar genera (-8kW), 3 cargas")
    fbs = ForwardBackwardSweep(ARCHIVO_RED)
    inyecciones = {
        1: (5000, 0),
        2: (3000, 500),
        3: (-8000, 0),
        4: (2000, 300),
        5: (1000, 200),
    }
    V, ok, it = fbs.resolver(inyecciones, tol=1e-8)
    return fbs, V, ok, it, inyecciones


def escenario_2():
    """Escenario noche: Solar=0, BESS compensa."""
    print("Escenario 2 (noche): Solar=0, BESS descarga a +10kW")
    fbs = ForwardBackwardSweep(ARCHIVO_RED)
    inyecciones = {
        1: (10000, 0),
        2: (3000, 500),
        3: (0, 0),
        4: (2000, 300),
        5: (1000, 200),
    }
    V, ok, it = fbs.resolver(inyecciones, tol=1e-8)
    return fbs, V, ok, it, inyecciones


def escenario_3():
    """Escenario sobrecarga: Solar=0, BESS=0, solo cargas."""
    print("Escenario 3 (sobrecarga): solo cargas, sin generacion")
    fbs = ForwardBackwardSweep(ARCHIVO_RED)
    inyecciones = {
        1: (0, 0),
        2: (3000, 500),
        3: (0, 0),
        4: (2000, 300),
        5: (1000, 200),
    }
    V, ok, it = fbs.resolver(inyecciones, tol=1e-8)
    return fbs, V, ok, it, inyecciones


def escenario_4():
    """Escenario excedente solar: Solar fuerte, BESS carga."""
    print("Escenario 4 (excedente solar): Solar -12kW, BESS carga +5kW")
    fbs = ForwardBackwardSweep(ARCHIVO_RED)
    inyecciones = {
        1: (-5000, 0),
        2: (3000, 500),
        3: (-12000, 0),
        4: (2000, 300),
        5: (1000, 200),
    }
    V, ok, it = fbs.resolver(inyecciones, tol=1e-8)
    return fbs, V, ok, it, inyecciones


def _mostrar(fbs, V, ok, it, inyecciones, titulo):
    print(f"\n{'='*60}")
    print(f"  {titulo}")
    print(f"  Convergio: {ok} | Iteraciones: {it}")
    print(f"{'='*60}")
    print(f"{'Nodo':>5} {'V[pu]':>8} {'V[V]':>10} {'P_inj[W]':>10} {'Q_inj[VAR]':>12}")
    print("-" * 50)
    for n in range(fbs.n_nodos):
        v_pu = abs(V[n])
        v_v = v_pu * fbs.v_base_nodo.get(n, 110.0)
        P, Q = inyecciones.get(n, (0, 0))
        print(f"{n:>5} {v_pu:>8.5f} {v_v:>10.2f} {P:>10.0f} {Q:>12.0f}")
    balance = sum(P for P, Q in inyecciones.values())
    print(f"{'Balance P:' :>20} {balance:>8.0f} W")
    print()


if __name__ == "__main__":
    print("=" * 60)
    print("  Test Solver FBS - Red de 6 Nodos")
    print("  Topologia: 0(Slack)-1(BESS)-2(L1)-3(Solar)-4(L2)-5(L3)")
    print("=" * 60)

    escenarios = [
        ("Base: BESS descarga + Solar gen", escenario_1()),
        ("Noche: Solar=0, BESS compensa", escenario_2()),
        ("Sobrecarga: solo cargas", escenario_3()),
        ("Excedente solar: Solar fuerte", escenario_4()),
    ]

    for titulo, (fbs, V, ok, it, iny) in escenarios:
        _mostrar(fbs, V, ok, it, iny, titulo)

    # Integracion con MasterClock
    print("=" * 60)
    print("  Integracion con MasterClock (5 pasos)")
    print("=" * 60)
    mc = MasterClock(archivo_red=ARCHIVO_RED, paso_maestro=0.1, modo="A")
    iny = {1: (5000, 0), 2: (3000, 500), 3: (-8000, 0),
           4: (2000, 300), 5: (1000, 200)}
    for n in iny:
        mc.registrar_inyeccion(n, *iny[n])
    for paso in range(5):
        V = mc.step()
        Vs = {n: f"{abs(V[n]):.5f}" for n in range(mc.nodos_red[0], 6)}
        print(f"  Paso {paso}: t={mc.tiempo:.1f}s | "
              f"V={Vs} [pu]")

    print("\n[OK] Test completado")
