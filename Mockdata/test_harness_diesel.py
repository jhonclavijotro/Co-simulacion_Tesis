"""Test harness para simular SistemaDiesel con consignas sinteticas.

Usa dos bucles anidados (multi-rate co-simulation):
  - Bucle externo: actualiza pref cada 500 ms desde el CSV
  - Bucle interno: ejecuta 500 pasos de 1 ms del modelo fisico

Uso:
    python Mockdata/test_harness_diesel.py
    python Mockdata/test_harness_diesel.py --full-24h
"""

import sys; sys.path.insert(0, ".")

import argparse
import numpy as np
import pandas as pd


def cargar_o_generar(ruta_csv="consignas_diesel_sinteticas.csv"):
    try:
        df = pd.read_csv(ruta_csv)
        print(f"Datos cargados: {len(df)} registros desde {ruta_csv}")
        return df
    except FileNotFoundError:
        print(f"Generando datos sinteticos...")
        from Mockdata.deepseek_data_diesel import df
        return df


def ventana(df, hora_inicio, hora_fin):
    t_seg = np.arange(0, 24 * 3600, 0.5)
    mask = (t_seg >= hora_inicio * 3600) & (t_seg < hora_fin * 3600)
    return df.iloc[mask].reset_index(drop=True)


def simular(df, estabilizar_s=2.0, max_pasos_internos=500, dt_interno=0.001):
    from Diesel.SistemaDiesel import SistemaDiesel

    sistema = SistemaDiesel()
    resultados = []
    errores = 0

    if len(df) == 0:
        return []

    if estabilizar_s > 0:
        n_estabilizar = int(estabilizar_s / dt_interno)
        sistema.pref = df.iloc[0]["pref"]
        for _ in range(n_estabilizar):
            sistema.step(dt_interno)
        print(f"Estabilizado durante {estabilizar_s:.1f}s "
              f"(pref={sistema.pref:.1f} rad/s)")

    n_csv = len(df)
    for idx, row in df.iterrows():
        sistema.pref = row["pref"]

        for _ in range(max_pasos_internos):
            try:
                ctx = sistema.step(dt_interno)
            except Exception as e:
                print(f"Error en fila CSV {idx}, t={sistema.contexto['time']:.3f}: {e}")
                errores += 1
                if errores > 10:
                    raise
                break

        if idx % 100 == 0 or idx == n_csv - 1:
            pct = (idx + 1) / n_csv * 100
            print(f"\r  Progreso: {idx+1}/{n_csv} filas ({pct:.0f}%)", end="")

        resultados.append(dict(ctx))

    print()
    return resultados


def validar(resultados, df):
    df_res = pd.DataFrame(resultados)

    corte = len(df_res) // 3
    df_res = df_res.iloc[corte:].reset_index(drop=True)
    df_corte = df.iloc[corte:].reset_index(drop=True)

    pref = df_corte["pref"].values
    wm = df_res["Wm"].values
    p_inj = df_res["Pw"].values
    v_dc = df_res["Vdc"].values
    p_dc_in = df_res["Pgen"].values

    checks = []

    # Wm debe seguir pref (correlacion alta)
    corr_wm = np.corrcoef(pref, wm)[0, 1]
    checks.append(("Correlacion pref vs Wm > 0.9", corr_wm > 0.9, f"{corr_wm:.3f}"))

    # Potencia no negativa
    p_min = p_inj.min()
    checks.append(("Pw positiva en regimen", p_min >= 0, f"{p_min:.1f} W"))

    # Vdc en rango
    v_dc_ee = v_dc[len(v_dc)//2:]
    checks.append(("Vdc en [250, 450] V",
                   v_dc_ee.min() >= 250 and v_dc_ee.max() <= 450,
                   f"[{v_dc_ee.min():.1f}, {v_dc_ee.max():.1f}] V"))

    # Pref sin valores extremos
    checks.append(("pref en rango [180, 200]",
                   pref.min() >= 180 and pref.max() <= 200,
                   f"[{pref.min():.1f}, {pref.max():.1f}]"))

    # Eficiencia
    p_inj_mean = p_inj.mean()
    p_in_mean = p_dc_in.mean()
    eff = p_inj_mean / p_in_mean if p_in_mean > 0 else 0.0
    checks.append(("Eficiencia sistema > 70%", eff > 0.70, f"{eff:.1%}"))

    print("\n--- Validaciones ---")
    todas_ok = True
    for nombre, ok, valor in checks:
        marca = "PASS" if ok else "FAIL"
        print(f"  [{marca}] {nombre}: {valor}")
        todas_ok = todas_ok and ok

    return todas_ok


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-24h", action="store_true",
                        help="Simular 24 horas completas")
    parser.add_argument("--inicio", type=float, default=12.0,
                        help="Hora de inicio (default: 12.0)")
    parser.add_argument("--fin", type=float, default=12.1,
                        help="Hora de fin (default: 12.1)")
    args = parser.parse_args()

    df = cargar_o_generar()

    if args.full_24h:
        df_ventana = df
    else:
        df_ventana = ventana(df, args.inicio, args.fin)
        print(f"Ventana seleccionada: {args.inicio:.1f}h a {args.fin:.1f}h "
              f"({len(df_ventana)} filas)")

    resultados = simular(df_ventana)

    ok = validar(resultados, df_ventana)

    sys.exit(0 if ok else 1)
