"""Test harness para simular SistemaSolar con datos meteorológicos sintéticos.

Usa dos bucles anidados (multi-rate co-simulation):
  - Bucle externo: actualiza POA y Tamb cada 500 ms desde el CSV
  - Bucle interno: ejecuta 500 pasos de 1 ms del modelo físico

Uso:
    python Mockdata/test_harness_solar.py
    python Mockdata/test_harness_solar.py --full-24h   # simulación completa
"""

import sys; sys.path.insert(0, ".")

import argparse
import numpy as np
import pandas as pd


def cargar_o_generar(ruta_csv="datos_meteorologicos_sinteticos.csv"):
    try:
        df = pd.read_csv(ruta_csv)
        print(f"Datos cargados: {len(df)} registros desde {ruta_csv}")
        return df
    except FileNotFoundError:
        print(f"Generando datos sintéticos...")
        from Mockdata.deepseek_data_solar import df
        return df


def ventana(df, hora_inicio, hora_fin):
    t_seg = np.arange(0, 24 * 3600, 0.5)
    mask = (t_seg >= hora_inicio * 3600) & (t_seg < hora_fin * 3600)
    return df.iloc[mask].reset_index(drop=True)


def simular(df, estabilizar_s=2.0, max_pasos_internos=500, dt_interno=0.001):
    from Solar.SistemaSolar import SistemaSolar

    sistema = SistemaSolar()
    resultados = []
    errores = 0

    # Período de estabilización antes de procesar datos del CSV
    # Usa la primera fila del DataFrame (que ya puede ser una ventana filtrada)
    if len(df) == 0:
        return []
    if estabilizar_s > 0:
        n_estabilizar = int(estabilizar_s / dt_interno)
        sistema.POA = df.iloc[0]["POA"]
        sistema.Tam = df.iloc[0]["T_amb"]
        for _ in range(n_estabilizar):
            sistema.step(dt_interno)
        print(f"Estabilizado durante {estabilizar_s:.1f}s "
              f"(POA={sistema.POA:.0f}, Tam={sistema.Tam:.1f}K)")

    n_csv = len(df)
    for idx, row in df.iterrows():
        sistema.POA = row["POA"]
        sistema.Tam = row["T_amb"]

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

    # Descartar primer tercio para evitar transitorio CSV (cambio de POA brusco)
    corte = len(df_res) // 3
    df_res = df_res.iloc[corte:].reset_index(drop=True)
    df_corte = df.iloc[corte:].reset_index(drop=True)

    poa = df_corte["POA"].values
    p_array = df_res["P_array"].values
    p_inj = df_res["Pw"].values
    v_dc = df_res["V_dc"].values

    checks = []

    mask_dia = poa > 50
    suficientes_puntos = mask_dia.sum() > 10

    if suficientes_puntos:
        corr = np.corrcoef(poa[mask_dia], p_array[mask_dia])[0, 1]
        checks.append(("Correlacion POA vs P_array > 0.9", corr > 0.9, f"{corr:.3f}"))
    else:
        checks.append(("Correlacion POA vs P_array", True, "skip (poca irradiancia)"))

    p_inj_positivo = p_inj[mask_dia] if suficientes_puntos else p_inj
    p_min = p_inj_positivo.min()
    checks.append(("Pw positiva en regimen", p_min >= 0, f"{p_min:.1f} W"))

    despues_calentamiento = len(v_dc) // 2
    v_dc_ee = v_dc[despues_calentamiento:]
    v_min, v_max = v_dc_ee.min(), v_dc_ee.max()
    checks.append(("V_dc en [350, 450] V en regimen",
                   v_min >= 350 and v_max <= 450,
                   f"[{v_min:.1f}, {v_max:.1f}] V"))

    poa_min = poa.min()
    checks.append(("POA sin negativos", poa_min >= 0, f"{poa_min:.1f} W/m2"))

    if suficientes_puntos:
        eff = p_inj[mask_dia].mean() / p_array[mask_dia].mean()
        checks.append(("Eficiencia inversor > 85%", eff > 0.85, f"{eff:.1%}"))
    else:
        checks.append(("Eficiencia inversor", True, "skip (poca irradiancia)"))

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
