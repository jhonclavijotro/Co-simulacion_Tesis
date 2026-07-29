"""Test harness para simular SistemaBESS con consignas sinteticas.

Dos modos:
  1. Modelo detallado (BESS/SistemaBESS.py) con BuckBoost + GridInverter
  2. Modelo simplificado (MAS/BESS_simplificado.py) para MAS

Usa multi-rate:
  - Bucle externo: actualiza P_ref cada 500 ms
  - Bucle interno: 500 pasos de 1 ms del modelo fisico

Uso:
    python Mockdata/test_harness_bess.py
    python Mockdata/test_harness_bess.py --mode detallado --full-24h
    python Mockdata/test_harness_bess.py --mode simplificado
"""

import sys; sys.path.insert(0, ".")

import argparse
import numpy as np


def generar_perfil_potencia(duracion_h=24, paso_externo=0.5):
    """Genera perfil sintetico de potencia para BESS.

    Ciclo tipico en una microrred:
      00:00-06:00  Carga lenta (SoC bajo, noche)
      06:00-08:00  Carga rapida (preparando para demanda)
      08:00-12:00  Descarga sostenida (pico matutino)
      12:00-14:00  Carga (excedente solar)
      14:00-18:00  Descarga (pico vespertino)
      18:00-20:00  Carga (noche, sobrante eolico)
      20:00-24:00  Descarga leve (pico nocturno)
    """
    t_total_s = duracion_h * 3600
    n_pasos = int(t_total_s / paso_externo)

    t_seg = np.arange(0, t_total_s, paso_externo)
    horas = t_seg / 3600.0

    # Perfil de P_ref en Watts (+ descarga, - carga)
    P_ref = np.zeros_like(horas)

    # Carga lenta nocturna
    mask = (horas >= 0) & (horas < 6)
    P_ref[mask] = -3000.0

    # Carga rapida
    mask = (horas >= 6) & (horas < 8)
    P_ref[mask] = -8000.0

    # Descarga pico matutino
    mask = (horas >= 8) & (horas < 12)
    P_ref[mask] = 6000.0

    # Carga por excedente solar
    mask = (horas >= 12) & (horas < 14)
    P_ref[mask] = -5000.0

    # Descarga pico vespertino
    mask = (horas >= 14) & (horas < 18)
    P_ref[mask] = 8000.0

    # Carga nocturna
    mask = (horas >= 18) & (horas < 20)
    P_ref[mask] = -4000.0

    # Descarga pico nocturno
    mask = (horas >= 20) & (horas < 24)
    P_ref[mask] = 3000.0

    return P_ref


def simular_sistema_detallado(P_ref, paso_externo=0.5, estabilizar_s=2.0):
    from BESS.SistemaBESS import SistemaBESS

    sistema = SistemaBESS(SoC_inicial=0.5, modo="promedio")
    resultados = []

    if estabilizar_s > 0:
        n_estab = int(estabilizar_s / 0.001)
        for _ in range(n_estab):
            sistema.step(0.001, setpoints={"P_ref_w": 0.0, "Q_ref_kvar": 0.0})
        print(f"  Estabilizado {estabilizar_s:.1f}s (Vdc={sistema.contexto['V_dc']:.1f}V)")

    n = len(P_ref)
    for idx, p_ref in enumerate(P_ref):
        try:
            ctx = sistema.step(paso_externo,
                               setpoints={"P_ref_w": p_ref, "Q_ref_kvar": 0.0})
        except Exception as e:
            print(f"  Error en paso {idx}, t={sistema.contexto['time']:.3f}: {e}")
            return resultados

        if idx % 1000 == 0 or idx == n - 1:
            pct = (idx + 1) / n * 100
            print(f"\r  Progreso: {idx+1}/{n} ({pct:.0f}%)", end="")

        resultados.append(dict(ctx))

    print()
    return resultados


def simular_simplificado(P_ref, dt_externo=0.5):
    from MAS.BESS_simplificado import BateriaSimplificada

    bess = BateriaSimplificada(SoC_inicial=0.5)
    resultados = []
    SoC = bess.SoC

    n = len(P_ref)
    for idx, p_ref in enumerate(P_ref):
        bess.step(dt_externo, p_ref)
        resultados.append({"SoC": bess.SoC, "P_ref": p_ref, "P_real": bess.P_real})

        if idx % 100 == 0 or idx == n - 1:
            pct = (idx + 1) / n * 100
            print(f"\r  Progreso: {idx+1}/{n} ({pct:.0f}%)", end="")

    print()
    return resultados


def validar_detallado(resultados):
    import pandas as pd
    df = pd.DataFrame(resultados)

    corte = len(df) // 3
    df_ee = df.iloc[corte:].reset_index(drop=True)

    checks = []

    # 1. SoC debe bajar con P_ref > 0 (descarga) y subir con P_ref < 0 (carga)
    soc = df["SoC"].values
    p_ref = df["P_ref"].values
    descarga = p_ref > 100
    carga = p_ref < -100
    if descarga.any():
        delta = np.diff(soc)[descarga[:-1]]
        checks.append(("SoC decrece en descarga", np.mean(delta) <= 0,
                       f"delta_medio={np.mean(delta):.6f}"))
    if carga.any():
        delta = np.diff(soc)[carga[:-1]]
        checks.append(("SoC crece en carga", np.mean(delta) >= 0,
                       f"delta_medio={np.mean(delta):.6f}"))

    # 2. Vdc en rango [360, 440]
    vdc = df["V_dc"].values
    vdc_ee = vdc[len(vdc)//2:]
    checks.append(("Vdc en [360, 440]V",
                   vdc_ee.min() >= 360 and vdc_ee.max() <= 440,
                   f"[{vdc_ee.min():.1f}, {vdc_ee.max():.1f}] V"))

    # 3. Duty en rango [-0.9, 0.9]
    duty = df["duty"].values
    checks.append(("Duty en [-0.9, 0.9]",
                   duty.min() >= -0.9 and duty.max() <= 0.9,
                   f"[{duty.min():.3f}, {duty.max():.3f}]"))

    # 4. SoC saturado en [0, 1]
    checks.append(("SoC en [0, 1]", soc.min() >= 0 and soc.max() <= 1,
                   f"[{soc.min():.3f}, {soc.max():.3f}]"))

    # 5. Pw sigue a P_ref en direccion (Pw < 0 durante carga de bateria)
    pw = df["Pw"].values
    # Ambos deben tener el mismo signo la mayoria del tiempo
    mismo_signo = np.mean((p_ref > 0) == (pw > 0))
    checks.append(("Pw mismo signo que P_ref > 80%", mismo_signo > 0.8,
                   f"coincidencia={mismo_signo:.1%}"))

    # 6. Potencia de bateria coherente con P_ref
    p_bat = df["P_bat"].values
    if np.std(p_ref) > 1 and np.std(p_bat) > 1:
        corr = np.corrcoef(p_ref, p_bat)[0, 1]
    else:
        corr = 1.0 if np.allclose(np.sign(p_ref), np.sign(p_bat)) else -1.0
    checks.append(("P_ref y P_bat correlacionadas", abs(corr) > 0.5,
                   f"r={corr:.3f}"))

    # 7. V_oc y V_bat consistentes con modo carga/descarga
    v_oc = df["V_oc"].values
    v_bat = df["V_bat"].values
    i_bat = df["I_bat"].values
    diff = v_oc - v_bat
    # Descarga (I>0): diff > 0. Carga (I<0): diff < 0
    consistency = np.mean((i_bat > 0) == (diff > 0))
    checks.append(("V_oc - V_bat signo consistente con I_bat > 80%",
                   consistency > 0.8, f"consistencia={consistency:.1%}"))

    return _reportar(checks)


def validar_simplificado(resultados):
    soc = np.array([r["SoC"] for r in resultados])
    p_ref = np.array([r["P_ref"] for r in resultados])

    checks = []

    # 1. SoC en [0, 1]
    checks.append(("SoC en [0, 1]", soc.min() >= 0 and soc.max() <= 1,
                   f"[{soc.min():.3f}, {soc.max():.3f}]"))

    # 2. SoC decrece en descarga
    descarga = p_ref > 100
    if descarga.any():
        delta = np.diff(soc)[descarga[:-1]]
        checks.append(("SoC decrece en descarga", np.mean(delta) <= 0,
                       f"delta_medio={np.mean(delta):.6f}"))

    # 3. SoC crece en carga
    carga = p_ref < -100
    if carga.any():
        delta = np.diff(soc)[carga[:-1]]
        checks.append(("SoC crece en carga", np.mean(delta) >= 0,
                       f"delta_medio={np.mean(delta):.6f}"))

    # 4. P_real = P_ref (siempre, modelo ideal)
    p_real = np.array([r["P_real"] for r in resultados])
    checks.append(("P_real = P_ref (ideal)", np.allclose(p_ref, p_real),
                   f"max_diff={np.max(np.abs(p_ref - p_real)):.1f}W"))

    # 5. Perdidas por eficiencia: P_chem difiere de P_ref segun modo
    E_wh = 480.0 * 200.0  # V_pack * capacidad_Ah (default)
    dt = 0.5
    dSoC_total = soc[-1] - soc[0]
    energia_quimica = -dSoC_total * E_wh * 3600
    p_chem = np.where(p_ref > 0, p_ref / 0.95, p_ref * 0.92)
    energia_efectiva = np.sum(p_chem * dt)
    error_energia = abs(energia_efectiva - energia_quimica)
    error_pct = error_energia / max(abs(energia_efectiva), 1) * 100
    checks.append(("Conservacion energia c/eficiencia < 1% error",
                   error_pct < 1.0,
                   f"error={error_pct:.3f}%"))

    return _reportar(checks)


def _reportar(checks):
    print("\n--- Validaciones ---")
    todas_ok = True
    for nombre, ok, valor in checks:
        marca = "PASS" if ok else "FAIL"
        print(f"  [{marca}] {nombre}: {valor}")
        todas_ok = todas_ok and ok
    return todas_ok


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test harness para SistemaBESS"
    )
    parser.add_argument("--mode", choices=["detallado", "simplificado"],
                        default="detallado",
                        help="Modelo a testear (default: detallado)")
    parser.add_argument("--full-24h", action="store_true",
                        help="Simular 24 horas completas")
    parser.add_argument("--duracion", type=float, default=0.5,
                        help="Duracion en horas (default: 0.5, 24h si --full-24h)")
    args = parser.parse_args()

    if args.full_24h:
        duracion = 24.0
    else:
        duracion = args.duracion

    print(f"Modo: {args.mode}")
    print(f"Duracion: {duracion:.1f}h")

    P_ref = generar_perfil_potencia(duracion)

    if args.mode == "detallado":
        resultados = simular_sistema_detallado(P_ref)
        if resultados:
            ok = validar_detallado(resultados)
        else:
            print("ERROR: Simulacion detallada no produjo resultados")
            ok = False
    else:
        resultados = simular_simplificado(P_ref)
        if resultados:
            ok = validar_simplificado(resultados)
        else:
            print("ERROR: Simulacion simplificada no produjo resultados")
            ok = False

    sys.exit(0 if ok else 1)
