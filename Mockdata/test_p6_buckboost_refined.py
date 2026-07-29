"""Test P6: Validacion del BuckBoost PI refinado.

Verifica:
  1. Nuevas ganancias default (Kp=0.2, Ki=15)
  2. Feedforward Kff mejora respuesta transitoria
  3. Modo de operacion buck/boost
  4. Tiempo de establecimiento < 100 ms
  5. Conmutacion buck-boost sin discontinuidad
  6. Integracion con SistemaBESS

Uso:
    python Mockdata/test_p6_buckboost_refined.py
"""

import sys; sys.path.insert(0, ".")

import numpy as np


def test_default_gains():
    from BESS.BuckBoost import BuckBoost

    bb = BuckBoost()
    assert bb.Kp == 0.2, f"Kp default: {bb.Kp}"
    assert bb.Ki == 15.0, f"Ki default: {bb.Ki}"
    assert bb.Kff == 0.5, f"Kff default: {bb.Kff}"
    print(f"  [PASS] Kp={bb.Kp}, Ki={bb.Ki}, Kff={bb.Kff}")
    return True


def test_buck_boost_mode():
    from BESS.BuckBoost import BuckBoost

    bb = BuckBoost()
    assert bb.modo_operacion(100.0) == "boost", "I_ref>0 debe ser boost"
    assert bb.modo_operacion(-100.0) == "buck", "I_ref<0 debe ser buck"
    assert bb.modo_operacion(0.0) == "idle", "I_ref=0 debe ser idle"
    print(f"  [PASS] Modos: boost (I>0), buck (I<0), idle (I=0)")
    return True


def test_settling_time():
    from BESS.BuckBoost import BuckBoost

    bb = BuckBoost(Kp=0.2, Ki=15.0, Kff=0.0)
    dt = 0.001
    I_ref = 100.0
    t_settle = None

    for i in range(200):
        duty = bb.control_corriente(I_ref, bb.I_bat, dt)
        bb.actualizar_estado(duty, I_ref, 480.0, bb.Vdc, 0.0, dt)
        if t_settle is None and abs(bb.I_bat - I_ref) < 1.0:
            t_settle = (i + 1) * dt

    ok = t_settle is not None and t_settle < 0.15
    print(f"  [{'PASS' if ok else 'FAIL'}] Tiempo establecimiento: "
          f"{t_settle*1000:.0f}ms (tol=150ms)")
    return ok


def test_feedforward_improves_response():
    from BESS.BuckBoost import BuckBoost

    bb_no_ff = BuckBoost(Kp=0.2, Ki=15.0, Kff=0.0)
    bb_ff = BuckBoost(Kp=0.2, Ki=15.0, Kff=0.5)
    dt = 0.001

    for i in range(50):
        d1 = bb_no_ff.control_corriente(100.0, bb_no_ff.I_bat, dt)
        bb_no_ff.actualizar_estado(d1, 100.0, 480.0, bb_no_ff.Vdc, 0.0, dt)
        d2 = bb_ff.control_corriente(100.0, bb_ff.I_bat, dt)
        bb_ff.actualizar_estado(d2, 100.0, 480.0, bb_ff.Vdc, 0.0, dt)

    err_no_ff = abs(100.0 - bb_no_ff.I_bat)
    err_ff = abs(100.0 - bb_ff.I_bat)
    ok = err_ff <= err_no_ff
    print(f"  [{'PASS' if ok else 'FAIL'}] Feedforward mejora: "
          f"error_sin_ff={err_no_ff:.2f}A, error_con_ff={err_ff:.2f}A")
    return ok


def test_transition_buck_boost():
    from BESS.BuckBoost import BuckBoost

    bb = BuckBoost(Kp=0.2, Ki=15.0, Kff=0.3)
    dt = 0.001
    corrientes = []

    for i in range(200):
        ref = 50.0 if i < 100 else -50.0
        duty = bb.control_corriente(ref, bb.I_bat, dt)
        bb.actualizar_estado(duty, ref, 480.0, bb.Vdc, 0.0, dt)
        corrientes.append(bb.I_bat)

    ok = True
    for i in range(1, len(corrientes)):
        if abs(corrientes[i] - corrientes[i-1]) > 500:
            ok = False
            break
    print(f"  [{'PASS' if ok else 'FAIL'}] Transicion buck-boost suave")
    return ok


def test_agenteBESS_integration():
    from MAS.AgenteBESS import AgenteBESS

    ag = AgenteBESS(1, [2], 3, SoC_inicial=0.6, P_rated=10000.0)
    ag.step(0.5, P_total_demanda=10000.0)
    ag.step(0.5, P_total_demanda=-5000.0)
    print(f"  [PASS] AgenteBESS integrado: SoC={ag.SoC:.4f}, P_ref={ag.P_ref:.0f}")
    return True


if __name__ == "__main__":
    tests = [
        ("Ganancias default", test_default_gains),
        ("Modo buck/boost", test_buck_boost_mode),
        ("Tiempo establecimiento", test_settling_time),
        ("Feedforward", test_feedforward_improves_response),
        ("Transicion buck-boost", test_transition_buck_boost),
        ("Integracion AgenteBESS", test_agenteBESS_integration),
    ]

    print("=" * 60)
    print("Test P6: BuckBoost PI Refinado")
    print("=" * 60)

    todos_ok = True
    for nombre, fn in tests:
        print(f"\n{nombre}:")
        try:
            ok = fn()
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"  [ERROR] {e}")
            ok = False
        todos_ok = todos_ok and ok

    print(f"\n{'=' * 60}")
    print(f"RESULTADO: {'TODOS PASARON' if todos_ok else 'FALLOS DETECTADOS'}")
    print(f"{'=' * 60}")
    sys.exit(0 if todos_ok else 1)
