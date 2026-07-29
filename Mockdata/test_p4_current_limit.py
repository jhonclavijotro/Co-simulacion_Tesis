"""Test P4: Validacion del limite de corriente del inversor en SistemaBESS.

Verifica:
  1. I_inv_max configurable via __init__ y property setter
  2. Limitacion dinamica: I_inv_lim se reduce con V_pcc < 0.85 pu
  3. Modo detallado tambien aplica limitacion
  4. Voltage sag V_pcc = 0.7 pu: I_inv recortado
  5. V_pcc = 1.0 pu: operacion normal sin recorte

Uso:
    python Mockdata/test_p4_current_limit.py
"""

import sys; sys.path.insert(0, ".")

import numpy as np


def test_I_inv_max_configurable():
    from BESS.SistemaBESS import SistemaBESS

    s1 = SistemaBESS(I_inv_max=30.0)
    assert s1.I_inv_max == 30.0, f"Esperado 30.0, obtenido {s1.I_inv_max}"

    s2 = SistemaBESS(I_inv_max=75.5)
    assert s2.I_inv_max == 75.5, f"Esperado 75.5, obtenido {s2.I_inv_max}"

    s3 = SistemaBESS()
    assert s3.I_inv_max == 50.0, f"Esperado 50.0 default, obtenido {s3.I_inv_max}"

    print(f"  [PASS] I_inv_max configurable: 30.0, 75.5, 50.0 (default)")
    return True


def test_I_inv_max_setter():
    from BESS.SistemaBESS import SistemaBESS

    s = SistemaBESS(I_inv_max=50.0)
    s.I_inv_max = 80.0
    assert s.I_inv_max == 80.0, f"Setter: esperado 80.0, obtenido {s.I_inv_max}"

    s.I_inv_max = -10.0
    assert s.I_inv_max == 0.0, f"Setter negativo: esperado 0.0, obtenido {s.I_inv_max}"

    print(f"  [PASS] Setter I_inv_max funciona (80.0, clamp negativo a 0)")
    return True


def test_current_limit_dynamic():
    from BESS.SistemaBESS import SistemaBESS

    s = SistemaBESS(I_inv_max=100.0)

    lim_1_0 = s._current_limit_dynamic(1.00)
    assert abs(lim_1_0 - 100.0) < 0.01, f"V_pcc=1.0: esperado 100.0, obtenido {lim_1_0}"

    lim_0_9 = s._current_limit_dynamic(0.90)
    assert abs(lim_0_9 - 100.0) < 0.01, f"V_pcc=0.9: esperado 100.0, obtenido {lim_0_9}"

    lim_0_85 = s._current_limit_dynamic(0.85)
    assert abs(lim_0_85 - 100.0) < 0.01, f"V_pcc=0.85: esperado 100.0, obtenido {lim_0_85}"

    lim_0_7 = s._current_limit_dynamic(0.70)
    esperado_0_7 = 100.0 * (0.70 - 0.50) / (0.85 - 0.50)
    assert abs(lim_0_7 - esperado_0_7) < 0.01, \
        f"V_pcc=0.7: esperado {esperado_0_7:.1f}, obtenido {lim_0_7:.1f}"

    lim_0_5 = s._current_limit_dynamic(0.50)
    assert abs(lim_0_5) < 0.01, f"V_pcc=0.5: esperado 0.0, obtenido {lim_0_5}"

    lim_0_3 = s._current_limit_dynamic(0.30)
    assert abs(lim_0_3) < 0.01, f"V_pcc=0.3: esperado 0.0, obtenido {lim_0_3}"

    print(f"  [PASS] Limitacion dinamica: "
          f"1.0pu={lim_1_0:.0f}, 0.85pu={lim_0_85:.0f}, "
          f"0.7pu={lim_0_7:.0f}, 0.5pu={lim_0_5:.0f}")
    return True


def test_voltage_sag_recorte_promedio():
    from BESS.SistemaBESS import SistemaBESS

    s = SistemaBESS(SoC_inicial=0.5, I_inv_max=50.0)
    dt = 0.001

    for _ in range(100):
        s.step(dt, V_pcc=110.0, setpoints={"P_ref_w": 5000.0, "Q_ref_kvar": 0.0})

    I_inv_normal = abs(s.contexto["I_inv_lim"])

    s2 = SistemaBESS(SoC_inicial=0.5, I_inv_max=50.0)
    for _ in range(100):
        s2.step(dt, V_pcc=77.0, setpoints={"P_ref_w": 5000.0, "Q_ref_kvar": 0.0})

    I_inv_sag = abs(s2.contexto["I_inv_lim"])

    ok_sag = I_inv_sag < I_inv_normal * 0.9
    print(f"  [{'PASS' if ok_sag else 'FAIL'}] Voltage sag 0.7pu: "
          f"I_lim_normal={I_inv_normal:.1f}A, I_lim_sag={I_inv_sag:.1f}A, "
          f"recorte={(1-I_inv_sag/I_inv_normal)*100:.0f}%")
    return ok_sag


def test_voltage_sag_modo_detallado():
    from BESS.SistemaBESS import SistemaBESS

    s = SistemaBESS(SoC_inicial=0.5, modo="detallado", I_inv_max=50.0)
    dt = 0.001

    for _ in range(100):
        s.step(dt, V_pcc=110.0, setpoints={"P_ref_w": 5000.0, "Q_ref_kvar": 0.0})

    I_inv_normal = abs(s.contexto["I_inv_lim"])

    s2 = SistemaBESS(SoC_inicial=0.5, modo="detallado", I_inv_max=50.0)
    for _ in range(100):
        s2.step(dt, V_pcc=77.0, setpoints={"P_ref_w": 5000.0, "Q_ref_kvar": 0.0})

    I_inv_sag = abs(s2.contexto["I_inv_lim"])

    ok = I_inv_sag < I_inv_normal * 0.9
    print(f"  [{'PASS' if ok else 'FAIL'}] Modo detallado sag 0.7pu: "
          f"I_lim_normal={I_inv_normal:.1f}A, I_lim_sag={I_inv_sag:.1f}A")
    return ok


def test_contexto_tracking():
    from BESS.SistemaBESS import SistemaBESS

    s = SistemaBESS(I_inv_max=50.0)
    ctx = s.step(0.001, V_pcc=110.0, setpoints={"P_ref_w": 0.0, "Q_ref_kvar": 0.0})

    assert "I_inv_lim" in ctx, "contexto debe tener I_inv_lim"
    assert ctx["I_inv_lim"] == 50.0, f"Esperado 50.0, obtenido {ctx['I_inv_lim']}"

    ctx2 = s.step(0.001, V_pcc=55.0, setpoints={"P_ref_w": 0.0, "Q_ref_kvar": 0.0})
    assert ctx2["I_inv_lim"] < 50.0, \
        f"I_inv_lim debe reducirse con V_pcc bajo: {ctx2['I_inv_lim']}"

    print(f"  [PASS] Contexto tracking: I_inv_lim={ctx['I_inv_lim']}A "
          f"(normal), {ctx2['I_inv_lim']:.1f}A (sag)")
    return True


if __name__ == "__main__":
    tests = [
        ("I_inv_max configurable", test_I_inv_max_configurable),
        ("Setter I_inv_max", test_I_inv_max_setter),
        ("Limitacion dinamica V_pcc", test_current_limit_dynamic),
        ("Voltage sag modo promedio", test_voltage_sag_recorte_promedio),
        ("Voltage sag modo detallado", test_voltage_sag_modo_detallado),
        ("Contexto tracking I_inv_lim", test_contexto_tracking),
    ]

    print("=" * 60)
    print("Test P4: Limite de Corriente del Inversor")
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
