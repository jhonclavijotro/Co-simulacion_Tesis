#!/usr/bin/env python3
"""
Generador de Figuras de Validación de la Co-Simulación HIL (S-40 / D-28)
======================================================================
Genera las 4 figuras solicitadas para el análisis y verificación del escenario
ESC-HIL-008_validacion_integrada ejecutado en el rack de Raspberry Pi 5:
  1. Perfil de tensión en los nodos (N1 a N8 en un solo gráfico)
  2. Perfil de radiación POA
  3. Frecuencia del sistema
  4. Perfil de demandas (cargas N4..N8, demanda total agregada y demanda neta en el mismo gráfico)

Formatos generados: PNG alta resolución (300 DPI) y PDF vectorial.
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# Configuración tipográfica y de estilo para publicación científica
matplotlib.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
    "font.size": 9.0,
    "axes.labelsize": 9.5,
    "axes.titlesize": 10.0,
    "xtick.labelsize": 8.5,
    "ytick.labelsize": 8.5,
    "legend.fontsize": 8.0,
    "figure.titlesize": 10.5,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "axes.linewidth": 0.8,
    "grid.linewidth": 0.5,
    "grid.alpha": 0.4,
    "grid.linestyle": ":",
    "lines.linewidth": 1.2,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.04
})

# Ancho estándar para figuras (en pulgadas)
FIG_WIDTH = 7.0  # 17.78 cm, ideal para lectura y reporte
DPI = 300

# Ventanas normativas del escenario ESC-HIL-008 para guías de eventos
VENTANAS = [
    (0, 40, "Convergencia\ninicial", "#f0f0f0"),
    (40, 100, "Régimen\nisócrono", "#f7fbff"),
    (100, 150, "Rampa\ncarga", "#fee8c8"),
    (150, 200, "Excedente 1\n(Escalón carga)", "#e5f5e0"),
    (200, 250, "Sombreado\nmoderado", "#fff7bc"),
    (250, 300, "Sombreado\nabrupto (Déficit)", "#fee0d2"),
    (300, 360, "Excedente 2\n(Recuperación)", "#e5f5e0"),
    (360, 410, "Pérdida 20%\nenlace 2-3", "#efedf5"),
    (410, 440, "Desconexión\ntotal 1-2", "#fcbba1"),
    (440, 480, "Cola limpia\nreconvergencia", "#f7fbff"),
]

def add_event_spans(ax, y_pos=None, show_labels=False):
    """Agrega fondos coloreados sutiles para las fases clave."""
    for ini, fin, lbl, col in VENTANAS:
        ax.axvspan(ini, fin, color=col, alpha=0.35, zorder=0)
        if show_labels and y_pos is not None:
            ax.text((ini + fin) / 2.0, y_pos, lbl, ha="center", va="top",
                    fontsize=6.5, color="#525252", zorder=5)


# -----------------------------------------------------------------------------
# 1. PERFIL DE TENSIÓN EN LOS NODOS (TODO EN UNA GRÁFICA)
# -----------------------------------------------------------------------------
def plot_voltages(df_telem, output_dirs):
    fig, ax = plt.subplots(figsize=(FIG_WIDTH, 4.0))

    t = df_telem["time_s"].values

    # Colores contrastantes para los 8 nodos
    colors = {
        "V1_pu": ("#1f77b4", "-", 1.4, "N1: Diésel (Slack)"),
        "V2_pu": ("#2ca02c", "-", 1.3, "N2: Solar PV"),
        "V3_pu": ("#9467bd", "-", 1.3, "N3: BESS"),
        "V4_pu": ("#ff7f0e", "--", 1.1, "N4: Carga A (Residencial)"),
        "V5_pu": ("#d62728", "--", 1.1, "N5: Carga B (Comercial)"),
        "V6_pu": ("#8c564b", "-.", 1.1, "N6: Carga C (Industrial)"),
        "V7_pu": ("#e377c2", ":", 1.2, "N7: Carga D (Residencial)"),
        "V8_pu": ("#17becf", ":", 1.2, "N8: Carga E (Comercial)"),
    }

    add_event_spans(ax)

    # Graficar cada barra
    for col, (color, ls, lw, label) in colors.items():
        ax.plot(t, df_telem[col].values, color=color, linestyle=ls, linewidth=lw, label=label, zorder=3)

    # Línea nominal 1.0 pu (400 V)
    ax.axhline(1.0, color="#252525", linestyle="-", linewidth=0.9, alpha=0.8, label="Nominal 1.00 p.u. (400 V)")

    # Cotas extremas
    v_cols = [f"V{i}_pu" for i in range(1, 9)]
    v_min_global = df_telem[v_cols].min().min()
    v_max_global = df_telem[v_cols].max().max()

    ax.annotate(f"Máx: {v_max_global:.4f} p.u. ({v_max_global*400:.2f} V)",
                xy=(320.0, v_max_global), xytext=(330.0, v_max_global + 0.0007),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#08519c"),
                fontsize=7.5, color="#08519c", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#08519c", lw=0.5))

    ax.annotate(f"Mín: {v_min_global:.4f} p.u. ({v_min_global*400:.2f} V)",
                xy=(180.0, v_min_global), xytext=(195.0, v_min_global - 0.0008),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#cb181d"),
                fontsize=7.5, color="#cb181d", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#cb181d", lw=0.5))

    # Eje secundario en Voltios
    secax = ax.secondary_yaxis('right', functions=(lambda x: x * 400.0, lambda x: x / 400.0))
    secax.set_ylabel("Tensión fase-fase $V_{\mathrm{LL}}$ [V]")
    secax.yaxis.set_major_locator(ticker.MultipleLocator(0.5))

    ax.set_xlabel("Tiempo $t$ [s]")
    ax.set_ylabel("Tensión nodal $V$ [p.u.]")
    ax.set_title("1. Perfil de Tensiones Nodales en el Tiempo (Nodos 1 a 8)", fontweight="bold")
    ax.set_xlim(-5, 485)
    ax.set_ylim(0.9990, 1.0055)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(50))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(0.001))
    ax.grid(True)

    # Leyenda en dos columnas arriba
    ax.legend(loc="upper right", framealpha=0.92, ncol=3, fontsize=7.2)

    # Nota de banda IEEE 1547
    ax.text(0.02, 0.05, "Banda normativa IEEE 1547 / NTC 1340: [0.95, 1.05] p.u. (desviación máxima medida < 0.45%)",
            transform=ax.transAxes, fontsize=7.2, style="italic", color="#252525",
            bbox=dict(boxstyle="square,pad=0.2", facecolor="#ffffff", alpha=0.9, edgecolor="#cccccc", lw=0.5))

    save_figure(fig, "fig_1_perfil_tension_nodos", output_dirs)
    plt.close(fig)


# -----------------------------------------------------------------------------
# 2. PERFIL DE RADIACIÓN POA
# -----------------------------------------------------------------------------
def plot_poa(df_meteo, output_dirs):
    fig, ax = plt.subplots(figsize=(FIG_WIDTH, 3.5))

    t = df_meteo["tiempo_s"].values
    poa = df_meteo["N2_POA_W_m2"].values

    add_event_spans(ax)

    # Señal de irradiancia
    ax.plot(t, poa, color="#d95f02", linewidth=1.5, label=r"Irradiancia en plano $G_{\mathrm{poa}}(t)$ [W/m²]", zorder=3)

    # Anotaciones de las zonas solares
    ax.annotate("Meseta inicial base\n836.8 W/m²",
                xy=(80.0, 836.8), xytext=(30.0, 680.0),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#252525"),
                fontsize=7.5, color="#252525",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#cccccc", lw=0.5))

    ax.annotate("Sombreado moderado\n587.0 W/m² (-29.8%)",
                xy=(225.0, 587.0), xytext=(170.0, 430.0),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#a63603"),
                fontsize=7.5, color="#a63603",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#a63603", lw=0.5))

    ax.annotate("Sombreado abrupto (Déficit)\n347.0 W/m² (-40.9%)",
                xy=(275.0, 347.0), xytext=(220.0, 200.0),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#cb181d"),
                fontsize=7.5, color="#cb181d",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#cb181d", lw=0.5))

    ax.annotate("Rampas de recuperación\n(300 a 315 s) → 765.5 W/m²",
                xy=(315.0, 765.5), xytext=(325.0, 580.0),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#2ca02c"),
                fontsize=7.5, color="#2ca02c",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#2ca02c", lw=0.5))

    ax.set_xlabel("Tiempo $t$ [s]")
    ax.set_ylabel(r"Irradiancia en plano $G_{\mathrm{poa}}$ [W/m²]")
    ax.set_title("2. Perfil de Radiación Solar en el Plano del Arreglo (POA)", fontweight="bold")
    ax.set_xlim(-5, 485)
    ax.set_ylim(150, 950)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(50))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(100))
    ax.grid(True)
    ax.legend(loc="upper right", framealpha=0.92, fontsize=7.8)

    save_figure(fig, "fig_2_perfil_radiacion_poa", output_dirs)
    plt.close(fig)


# -----------------------------------------------------------------------------
# 3. FRECUENCIA DEL SISTEMA
# -----------------------------------------------------------------------------
def plot_frequency(df_telem, output_dirs):
    fig, ax = plt.subplots(figsize=(FIG_WIDTH, 3.8))

    t = df_telem["time_s"].values
    f = df_telem["f_sys_hz"].values

    add_event_spans(ax)

    # Banda normativa ±0.1 Hz
    ax.axhspan(59.9, 60.1, color="#2ca25f", alpha=0.15, label=r"Banda continua IEEE 1547 / NTC 1340 ($\pm 0.1$ Hz)", zorder=1)
    # Consigna nominal 60.0 Hz
    ax.axhline(60.0, color="#252525", linestyle="--", linewidth=0.9, alpha=0.8, label="Frecuencia nominal 60.00 Hz", zorder=2)
    # Límites NTC 1340
    ax.axhline(58.8, color="#cb181d", linestyle="-.", linewidth=0.8, alpha=0.7, label="Límite emergencia NTC 1340 (58.80 Hz)", zorder=2)

    # Señal principal de frecuencia
    ax.plot(t, f, color="#08519c", linewidth=1.3, label=r"Frecuencia medida $f_{\mathrm{sys}}(t)$", zorder=4)

    # Anotaciones
    f_min = f.min()
    t_f_min = t[np.argmin(f)]
    f_max = f.max()
    t_f_max = t[np.argmax(f)]

    ax.annotate(f"Mínimo: {f_min:.3f} Hz (t={t_f_min:.1f} s)\n(Rampa de carga)",
                xy=(t_f_min, f_min), xytext=(t_f_min + 15, f_min - 0.25),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#cb181d"),
                fontsize=7.5, color="#cb181d", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#cb181d", lw=0.5))

    ax.annotate(f"Pico: {f_max:.3f} Hz (t={t_f_max:.1f} s)\n(Acoplamiento inicial)",
                xy=(t_f_max, f_max), xytext=(t_f_max + 20, f_max + 0.12),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#08519c"),
                fontsize=7.5, color="#08519c", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#08519c", lw=0.5))

    ax.annotate(f"Excedente 1: 60.41 Hz (t=160 s)\n(BESS absorbe a -3.0 kW)",
                xy=(160.0, 60.412), xytext=(170.0, 60.65),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#2ca02c"),
                fontsize=7.2, color="#2ca02c",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#2ca02c", lw=0.5))

    ax.annotate("Corte enlace 1-2 (410-440 s)\nEstabilidad preservada",
                xy=(425.0, 60.0), xytext=(350.0, 59.35),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#6a51a3"),
                fontsize=7.2, color="#6a51a3",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#6a51a3", lw=0.5))

    ax.set_xlabel("Tiempo $t$ [s]")
    ax.set_ylabel(r"Frecuencia $f_{\mathrm{sys}}$ [Hz]")
    ax.set_title("3. Frecuencia del Sistema y Regulación Isócrona en el Banco HIL", fontweight="bold")
    ax.set_xlim(-5, 485)
    ax.set_ylim(59.1, 60.9)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(50))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(0.2))
    ax.grid(True)
    ax.legend(loc="lower left", framealpha=0.92, ncol=2, fontsize=7.5)

    save_figure(fig, "fig_3_frecuencia_sistema", output_dirs)
    plt.close(fig)


# -----------------------------------------------------------------------------
# 4. PERFIL DE DEMANDAS (INDIVIDUALES, TOTAL Y DEMANDA NETA EN EL MISMO GRÁFICO)
# -----------------------------------------------------------------------------
def plot_demands(df_telem, df_demand, output_dirs):
    fig, ax = plt.subplots(figsize=(FIG_WIDTH, 4.3))

    t = df_demand["tiempo_s"].values

    # Demandas por nodo individual
    p4 = df_demand["N4_P_kW"].values
    p5 = df_demand["N5_P_kW"].values
    p6 = df_demand["N6_P_kW"].values
    p7 = df_demand["N7_P_kW"].values
    p8 = df_demand["N8_P_kW"].values

    p_load_total = p4 + p5 + p6 + p7 + p8

    # Potencia solar y demanda neta (P_load_total - P_solar)
    p_solar = df_telem["P2_kW"].values
    p_demanda_neta = p_load_total - p_solar
    p_net_grid = df_telem["P_net_kW"].values

    add_event_spans(ax)

    # 1. Curvas individuales de cargas (líneas delgadas y claras)
    ax.plot(t, p4, color="#aec7e8", linestyle="-", linewidth=1.0, alpha=0.9, label="Carga N4 (Residencial)")
    ax.plot(t, p5, color="#ffbb78", linestyle="-", linewidth=1.0, alpha=0.9, label="Carga N5 (Comercial)")
    ax.plot(t, p6, color="#c5b0d5", linestyle="-", linewidth=1.0, alpha=0.9, label="Carga N6 (Industrial)")
    ax.plot(t, p7, color="#f7b6d2", linestyle="-", linewidth=1.0, alpha=0.9, label="Carga N7 (Residencial)")
    ax.plot(t, p8, color="#c7c7c7", linestyle="-", linewidth=1.0, alpha=0.9, label="Carga N8 (Comercial)")

    # 2. Demanda Total de Cargas (línea sólida azul marino gruesa)
    ax.plot(t, p_load_total, color="#08519c", linestyle="-", linewidth=2.0, label=r"Demanda total agregada $P_{\mathrm{carga, total}}(t)$", zorder=4)

    # 3. Demanda Neta vista por la red: P_load - P_solar (línea magenta discontinua gruesa)
    ax.plot(t, p_demanda_neta, color="#7a0177", linestyle="--", linewidth=2.0, label=r"Demanda neta $P_{\mathrm{neta}}(t) = P_{\mathrm{carga}} - P_{\mathrm{PV}}$", zorder=4)

    # 4. Desbalance neto de la microrred (P_gen - P_demanda) para contexto
    ax.plot(t, p_net_grid, color="#006d2c", linestyle="-.", linewidth=1.2, alpha=0.85, label=r"Desbalance neto red $P_{\mathrm{net}}(t) = \sum P_{\mathrm{gen}} - P_{\mathrm{carga}}$", zorder=3)

    # Línea de balance cero
    ax.axhline(0.0, color="#525252", linestyle=":", linewidth=0.8, alpha=0.6)

    # Anotaciones
    ax.annotate("Escalón negativo de carga\n(150 s): Caída a ~4.0 kW",
                xy=(152.0, 4.0), xytext=(60.0, 2.0),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#08519c"),
                fontsize=7.5, color="#08519c",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#08519c", lw=0.5))

    ax.annotate("Excedente 1: Demanda neta cae a ~1.0 kW\n(Solar cubre ~80% de demanda)",
                xy=(170.0, p_demanda_neta[340]), xytext=(120.0, -1.8),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#7a0177"),
                fontsize=7.2, color="#7a0177",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#7a0177", lw=0.5))

    ax.annotate("Déficit severo (250-300 s)\nDemanda neta repunta a ~9.5 kW\n(Caída simultánea solar)",
                xy=(275.0, 9.4), xytext=(220.0, 11.2),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#cb181d"),
                fontsize=7.2, color="#cb181d",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#cb181d", lw=0.5))

    ax.set_xlabel("Tiempo $t$ [s]")
    ax.set_ylabel("Potencia activa $P$ [kW]")
    ax.set_title("4. Perfil de Demandas por Nodo, Demanda Agregada Total y Demanda Neta", fontweight="bold")
    ax.set_xlim(-5, 485)
    ax.set_ylim(-3.5, 13.0)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(50))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(2.0))
    ax.grid(True)

    # Leyenda en dos columnas arriba
    ax.legend(loc="upper right", framealpha=0.92, ncol=2, fontsize=7.2)

    save_figure(fig, "fig_4_perfil_demandas_y_demanda_neta", output_dirs)
    plt.close(fig)


def save_figure(fig, base_name, output_dirs):
    for out_dir in output_dirs:
        os.makedirs(out_dir, exist_ok=True)
        pdf_path = os.path.join(out_dir, f"{base_name}.pdf")
        png_path = os.path.join(out_dir, f"{base_name}.png")
        fig.savefig(pdf_path, format="pdf", bbox_inches="tight")
        fig.savefig(png_path, format="png", dpi=DPI, bbox_inches="tight")
        print(f"[OK] Guardada: {pdf_path}")
        print(f"[OK] Guardada: {png_path}")


def main():
    root = "D:/Antigravity/Projects/Tesis_Grado"
    telem_path = os.path.join(root, "outputs/validation/results/20261114T082959_ESC-HIL-008_validacion_integrada_seed42/telemetry_rack.csv")
    meteo_path = os.path.join(root, "Forms/escenarios_generados/ESC-HIL-008_validacion_integrada/datos_meteorologicos.csv")
    demand_path = os.path.join(root, "Forms/escenarios_generados/ESC-HIL-008_validacion_integrada/datos_demanda.csv")

    output_dirs = [
        os.path.join(root, "outputs/validation/results/20261114T082959_ESC-HIL-008_validacion_integrada_seed42/figures"),
        os.path.join(root, "outputs/validation/figures"),
        "D:/TEXTOS/TESIS/Figuras/validacion_s40"
    ]

    print("Cargando datos de simulación...")
    df_telem = pd.read_csv(telem_path)
    df_meteo = pd.read_csv(meteo_path)
    df_demand = pd.read_csv(demand_path)

    print("\nGenerando Figura 1: Tensiones Nodales...")
    plot_voltages(df_telem, output_dirs)

    print("\nGenerando Figura 2: Radiación POA...")
    plot_poa(df_meteo, output_dirs)

    print("\nGenerando Figura 3: Frecuencia del Sistema...")
    plot_frequency(df_telem, output_dirs)

    print("\nGenerando Figura 4: Demandas y Demanda Neta...")
    plot_demands(df_telem, df_demand, output_dirs)

    print("\n[ÉXITO] Las 4 figuras han sido generadas en formato PNG (300 DPI) y PDF vectorial.")

if __name__ == "__main__":
    main()
