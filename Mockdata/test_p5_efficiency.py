"""Test P5: Validacion de eficiencia round-trip en BESS_simplificado.

Verifica:
  1. eta_charge y eta_discharge configurables en __init__
  2. SoC decrece mas rapido con eta_discharge < 1 (descarga con perdidas)
  3. SoC crece mas lento con eta_charge < 1 (carga con perdidas)
  4. En ciclo completo: energia extraida > energia almacenada
  5. Valores default correctos

Uso:
    python Mockdata/test_p5_efficiency.py
"""

import sys; sys.path.insert(0, ".")

import numpy as np


def test_default_eta_values():
    from MAS.BESS_simplificado import BateriaSimplificada

    b = BateriaSimplificada()
    assert abs(b.eta_charge - 0.92) < 1e-6, f"eta_charge default: {b.eta_charge}"
    assert abs(b.eta_discharge - 0.95) < 1e-6, f"eta_discharge default: {b.eta_discharge}"
    print(f"  [PASS] eta_charge={b.eta_charge}, eta_discharge={b.eta_discharge} (default)")
    return True


def test_custom_eta_values():
    from MAS.BESS_simplificado import BateriaSimplificada

    b = BateriaSimplificada(eta_charge=0.85, eta_discharge=0.90)
    assert abs(b.eta_charge - 0.85) < 1e-6
    assert abs(b.eta_discharge - 0.90) < 1e-6
    print(f"  [PASS] eta_charge={b.eta_charge}, eta_discharge={b.eta_discharge} (custom)")
    return True


def test_discharge_faster_with_losses():
    from MAS.BESS_simplificado import BateriaSimplificada

    b_ideal = BateriaSimplificada(SoC_inicial=0.8, eta_charge=1.0, eta_discharge=1.0)
    b_loss = BateriaSimplificada(SoC_inicial=0.8, eta_charge=0.92, eta_discharge=0.95)

    dt = 0.5
    for _ in range(200):
        b_ideal.step(dt, 5000.0)
        b_loss.step(dt, 5000.0)

    ok = b_loss.SoC < b_ideal.SoC
    print(f"  [{'PASS' if ok else 'FAIL'}] Descarga con perdidas: "
          f"SoC_ideal={b_ideal.SoC:.4f}, SoC_loss={b_loss.SoC:.4f}")
    return ok


def test_charge_slower_with_losses():
    from MAS.BESS_simplificado import BateriaSimplificada

    b_ideal = BateriaSimplificada(SoC_inicial=0.5, eta_charge=1.0, eta_discharge=1.0)
    b_loss = BateriaSimplificada(SoC_inicial=0.5, eta_charge=0.92, eta_discharge=0.95)

    dt = 0.5
    for _ in range(200):
        b_ideal.step(dt, -5000.0)
        b_loss.step(dt, -5000.0)

    ok = b_loss.SoC < b_ideal.SoC
    print(f"  [{'PASS' if ok else 'FAIL'}] Carga con perdidas: "
          f"SoC_ideal={b_ideal.SoC:.4f}, SoC_loss={b_loss.SoC:.4f}")
    return ok


def test_round_trip_energy_loss():
    from MAS.BESS_simplificado import BateriaSimplificada

    b = BateriaSimplificada(SoC_inicial=0.6, eta_charge=0.92, eta_discharge=0.95)
    dt = 0.5
    E_wh = b.E_wh

    SoC_inicial = b.SoC

    for _ in range(400):
        b.step(dt, 5000.0)

    for _ in range(400):
        b.step(dt, -5000.0)

    SoC_final = b.SoC
    perdida_energia = (SoC_inicial - SoC_final) * E_wh * 3600
    ok = perdida_energia > 100
    print(f"  [{'PASS' if ok else 'FAIL'}] Perdida round-trip: "
          f"SoC {SoC_inicial:.4f} -> {SoC_final:.4f}, "
          f"energia perdida={perdida_energia:.0f}Wh")
    return ok


def test_ideal_no_losses():
    from MAS.BESS_simplificado import BateriaSimplificada

    b = BateriaSimplificada(SoC_inicial=0.6, eta_charge=1.0, eta_discharge=1.0)
    dt = 0.5
    SoC_ini = b.SoC

    for _ in range(400):
        b.step(dt, 5000.0)
    for _ in range(400):
        b.step(dt, -5000.0)

    ok = abs(b.SoC - SoC_ini) < 1e-6
    print(f"  [{'PASS' if ok else 'FAIL'}] Sin perdidas: "
          f"SoC {SoC_ini:.4f} -> {b.SoC:.4f}")
    return ok


def test_AgenteBESS_integration():
    from MAS.AgenteBESS import AgenteBESS

    ag = AgenteBESS(1, [2], 3, SoC_inicial=0.7, P_rated=10000.0)
    assert hasattr(ag.bateria, "eta_charge"), "AgenteBESS debe tener eta_charge"
    assert hasattr(ag.bateria, "eta_discharge"), "AgenteBESS debe tener eta_discharge"
    print(f"  [PASS] AgenteBESS integrado: eta_c={ag.bateria.eta_charge}, "
          f"eta_d={ag.bateria.eta_discharge}")
    return True


if __name__ == "__main__":
    tests = [
        ("Valores default eta", test_default_eta_values),
        ("Eta personalizados", test_custom_eta_values),
        ("Descarga mas rapida con perdidas", test_discharge_faster_with_losses),
        ("Carga mas lenta con perdidas", test_charge_slower_with_losses),
        ("Perdida round-trip", test_round_trip_energy_loss),
        ("Sin perdidas = conservacion", test_ideal_no_losses),
        ("Integracion AgenteBESS", test_AgenteBESS_integration),
    ]

    print("=" * 60)
    print("Test P5: Eficiencia Round-Trip BESS_simplificado")
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
