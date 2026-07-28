"""Test harness para simular SistemaHidrico con datos hidrologicos sinteticos.

Usa dos bucles anidados (multi-rate co-simulation):
  - Bucle externo: actualiza Vc cada 500 ms desde el CSV
  - Bucle interno: ejecuta 500 pasos de 1 ms del modelo fisico

Uso:
    python Mockdata/test_harness_hidrico.py
    python Mockdata/test_harness_hidrico.py --full-24h   # simulacion completa
"""

import sys; sys.path.insert(0, ".")

import argparse
import numpy as np
import pandas as pd


def cargar_o_generar(ruta_csv="datos_meteorologicos_hidricos_sinteticos.csv"):
    try:
        df = pd.read_csv(ruta_csv)
        print(f"Datos cargados: {len(df)} registros desde {ruta_csv}")
        return df
    except FileNotFoundError:
        print(f"Generando datos sinteticos...")
        from Mockdata.deepseek_data_hidrico import df
        return df


def ventana(df, hora_inicio, hora_fin):
    t_seg = np.arange(0, 24 * 3600, 0.5)
    mask = (t_seg >= hora_inicio * 3600) & (t_seg < hora_fin * 3600)
    return df.iloc[mask].reset_index(drop=True)


def simular(df, estabilizar_s=2.0, max_pasos_internos=500, dt_interno=0.001):
    from Hidrica.SistemaHidrico import SistemaHidrico

    sistema = SistemaHidrico()
    resultados = []
    errores = 0

    if len(df) == 0:
        return []

    # Estabilizacion inicial con el primer valor de corriente
    if estabilizar_s > 0:
        n_estabilizar = int(estabilizar_s / dt_interno)
        sistema.Vc = df.iloc[0]["Vc"]
        for _ in range(n_estabilizar):
            sistema.step(dt_interno)
        print(f"Estabilizado durante {estabilizar_s:.1f}s "
              f"(Vc={sistema.Vc:.1f} m/s)")

    n_csv = len(df)
    for idx, row in df.iterrows():
        sistema.Vc = row["Vc"]

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

    # Descartar primer tercio para evitar transitorio
    corte = len(df_res) // 3
    df_res = df_res.iloc[corte:].reset_index(drop=True)
    df_corte = df.iloc[corte:].reset_index(drop=True)

    vc = df_corte["Vc"].values
    p_inj = df_res["Pw"].values
    v_dc = df_res["Vdc"].values
    p_dc_in = df_res["Pdc_in"].values

    checks = []

    # Correlacion Vc vs Pw (deberia ser alta: mas caudal -> mas potencia)
    corr = np.corrcoef(vc, p_inj)[0, 1]
    checks.append(("Correlacion Vc vs Pw > 0.8", corr > 0.8, f"{corr:.3f}"))

    # Potencia inyectada no negativa
    p_min = p_inj.min()
    checks.append(("Pw positiva en regimen", p_min >= 0, f"{p_min:.1f} W"))

    # Vdc en rango estable
    despues_calentamiento = len(v_dc) // 2
    v_dc_ee = v_dc[despues_calentamiento:]
    v_min, v_max = v_dc_ee.min(), v_dc_ee.max()
    checks.append(("Vdc en [250, 450] V en regimen",
                   v_min >= 250 and v_max <= 450,
                   f"[{v_min:.1f}, {v_max:.1f}] V"))

    # Vc sin negativos
    vc_min = vc.min()
    checks.append(("Vc sin negativos", vc_min >= 0, f"{vc_min:.1f} m/s"))

    # Eficiencia del sistema (Pw / Pdc_in)
    p_inj_mean = p_inj.mean()
    p_in_mean = p_dc_in.mean()
    if p_in_mean > 0:
        eff = p_inj_mean / p_in_mean
    else:
        eff = 0.0
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
