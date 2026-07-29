"""Test P3: Validacion del PI con anti-windup en BuckBoost.

Verifica:
  1. Error estacionario nulo con P_ref escalon constante
  2. Anti-windup: sin overshoot en saturacion tras escalon grande
  3. Duty dentro de limites configurables [d_min, d_max]
  4. Seguimiento sinusoidal sin distorsion por windup
  5. Reset de integral via reset_integral()

Uso:
    python Mockdata/test_p3_buckboost_pi.py
"""

import sys; sys.path.insert(0, ".")

import math
import numpy as np


def test_steady_state_zero_error():
    from BESS.BuckBoost import BuckBoost

    bb = BuckBoost(Kp=0.1, Ki=0.5)
    dt = 0.001
    I_bat_ref = 50.0
    n_steps = int(1.0 / dt)

    for i in range(n_steps):
        duty = bb.control_corriente(I_bat_ref, bb.I_bat, dt)
        bb.actualizar_estado(duty, I_bat_ref, 480.0, bb.Vdc, 0.0, dt)

    error = abs(I_bat_ref - bb.I_bat)
    tolerancia = 0.05
    ok = error < tolerancia
    print(f"  [{'PASS' if ok else 'FAIL'}] Error estacionario: I_bat={bb.I_bat:.3f}A, "
          f"ref={I_bat_ref}A, error={error:.4f}A (tol={tolerancia})")
    return ok


def test_anti_windup_no_overshoot():
    from BESS.BuckBoost import BuckBoost

    bb = BuckBoost(Kp=0.05, Ki=0.3, d_min=-0.9, d_max=0.9)
    dt = 0.001

    I_bat_ref = 500.0
    n_saturacion = int(0.5 / dt)
    for i in range(n_saturacion):
        duty = bb.control_corriente(I_bat_ref, bb.I_bat, dt)
        bb.actualizar_estado(duty, I_bat_ref, 480.0, bb.Vdc, 0.0, dt)

    I_bat_peak = bb.I_bat

    I_bat_ref = 50.0
    n_recuperacion = int(1.0 / dt)
    for i in range(n_recuperacion):
        duty = bb.control_corriente(I_bat_ref, bb.I_bat, dt)
        bb.actualizar_estado(duty, I_bat_ref, 480.0, bb.Vdc, 0.0, dt)

    I_bat_final = bb.I_bat
    overshoot = max(0.0, (I_bat_final - I_bat_ref) / I_bat_ref * 100)
    ok = overshoot < 5.0
    print(f"  [{'PASS' if ok else 'FAIL'}] Anti-windup: I_bat_final={I_bat_final:.2f}A, "
          f"ref={I_bat_ref}A, overshoot={overshoot:.1f}% (tol=5%)")
    return ok


def test_duty_within_limits():
    from BESS.BuckBoost import BuckBoost

    bb = BuckBoost(Kp=0.1, Ki=0.5, d_min=-0.8, d_max=0.8)
    dt = 0.001

    for ref in [100.0, -100.0, 500.0, -500.0]:
        duty = bb.control_corriente(ref, 0.0, dt)
        ok = -0.801 <= duty <= 0.801
        if not ok:
            print(f"  [FAIL] Duty={duty:.4f} fuera de limites [-0.8, 0.8] para ref={ref}")
            return False

    print(f"  [PASS] Duty dentro de limites [-0.8, 0.8] en todos los casos")
    return True


def test_sine_tracking_no_windup():
    from BESS.BuckBoost import BuckBoost

    bb = BuckBoost(Kp=0.1, Ki=0.5, d_min=-0.9, d_max=0.9)
    dt = 0.001
    t = np.arange(0, 2.0, dt)
    I_ref_sin = 50.0 * np.sin(2 * math.pi * 2.0 * t)

    errors = []
    for i in range(len(t)):
        duty = bb.control_corriente(I_ref_sin[i], bb.I_bat, dt)
        bb.actualizar_estado(duty, I_ref_sin[i], 480.0, bb.Vdc, 0.0, dt)
        errors.append(abs(I_ref_sin[i] - bb.I_bat))

    mae = np.mean(errors)
    ok = mae < 5.0
    print(f"  [{'PASS' if ok else 'FAIL'}] Seguimiento sinusoidal: MAE={mae:.3f}A (tol=5.0A)")
    return ok


def test_reset_integral():
    from BESS.BuckBoost import BuckBoost

    bb = BuckBoost(Kp=0.1, Ki=0.5)
    bb.control_corriente(100.0, 0.0, 0.001)
    bb.control_corriente(100.0, 0.0, 0.001)

    bb.reset_integral()
    ok = bb.integral == 0.0
    print(f"  [{'PASS' if ok else 'FAIL'}] Reset integral: valor={bb.integral}")
    return ok


if __name__ == "__main__":
    tests = [
        ("Error estacionario nulo", test_steady_state_zero_error),
        ("Anti-windup sin overshoot", test_anti_windup_no_overshoot),
        ("Duty dentro de limites", test_duty_within_limits),
        ("Seguimiento sinusoidal", test_sine_tracking_no_windup),
        ("Reset de integral", test_reset_integral),
    ]

    print("=" * 60)
    print("Test P3: PI con Anti-Windup en BuckBoost")
    print("=" * 60)

    todos_ok = True
    for nombre, fn in tests:
        print(f"\n{nombre}:")
        try:
            ok = fn()
        except Exception as e:
            print(f"  [ERROR] {e}")
            ok = False
        todos_ok = todos_ok and ok

    print(f"\n{'=' * 60}")
    print(f"RESULTADO: {'TODOS PASARON' if todos_ok else 'FALLOS DETECTADOS'}")
    print(f"{'=' * 60}")
    sys.exit(0 if todos_ok else 1)
