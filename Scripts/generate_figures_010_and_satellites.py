#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generador de Figuras de Validación HIL para ESC-HIL-010 y Satélites ESC-HIL-011a/b
================================================================================
Genera las 4 figuras clave solicitadas para ESC-HIL-010 (660 s):
  1. Perfil de tensión en los nodos (N1 a N8 en un solo gráfico)
  2. Perfil de radiación POA (sombreados suave y abrupto)
  3. Frecuencia del sistema (análisis de oscilaciones sostenidas)
  4. Perfil de demandas (cargas N4..N8, agregada total y neta en el mismo gráfico)
Y la figura 5 complementaria para los ensayos satélite:
  5. Dinámica de frecuencia y potencias en satélites 011a (SoC alto) y 011b (SoC bajo)
"""

import os
import sys
import shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# Estilo para publicación científica
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

FIG_WIDTH = 7.2  # Pulgadas
DPI = 300

# Bloques principales de ESC-HIL-010 para sombreado de fondo
BLOQUES_010 = [
    (0, 40, "A: Inicio", "#f0f0f0"),
    (40, 100, "B: +30% Carga", "#fee8c8"),
    (100, 160, "C: -30% Carga", "#e5f5e0"),
    (160, 210, "D: Nominal", "#f7fbff"),
    (210, 290, "E: Sombreado Suave\n(833→560→833)", "#fff7bc"),
    (290, 320, "D': Nominal", "#f7fbff"),
    (320, 400, "F: Sombreado Abrupto\n(833→347→833)", "#fee0d2"),
    (400, 430, "D'': Nominal", "#f7fbff"),
    (430, 480, "G: Pérdida 2-3\n(+Q en 440s)", "#efedf5"),
    (480, 510, "H: Reconexión 2-3", "#f7fbff"),
    (510, 540, "I: Corte 1-2 (30s)", "#fcbba1"),
    (540, 570, "I': Reconexión 1-2", "#f7fbff"),
    (570, 600, "J: +25% Carga", "#fee8c8"),
    (600, 660, "K: Cola Limpia", "#f7fbff"),
]

def add_event_spans_010(ax, y_pos=None, show_labels=False):
    for ini, fin, lbl, col in BLOQUES_010:
        ax.axvspan(ini, fin, color=col, alpha=0.35, zorder=0)
        if show_labels and y_pos is not None:
            ax.text((ini + fin) / 2.0, y_pos, lbl, ha="center", va="top",
                    fontsize=6.0, color="#525252", zorder=5)


# -----------------------------------------------------------------------------
# 1. PERFIL DE TENSIÓN EN LOS NODOS (ESC-HIL-010)
# -----------------------------------------------------------------------------
def plot_voltages_010(df_telem, output_dirs):
    fig, ax = plt.subplots(figsize=(FIG_WIDTH, 4.2))
    t = df_telem["time_s"].values

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

    add_event_spans_010(ax)

    for col, (color, ls, lw, label) in colors.items():
        ax.plot(t, df_telem[col].values, color=color, linestyle=ls, linewidth=lw, label=label, zorder=3)

    ax.axhline(1.0, color="#252525", linestyle="-", linewidth=0.9, alpha=0.8, label="Nominal 1.00 p.u. (400 V)")

    v_cols = [f"V{i}_pu" for i in range(1, 9)]
    v_min_global = df_telem[v_cols].min().min()
    v_max_global = df_telem[v_cols].max().max()

    ax.annotate(f"Máx global: {v_max_global:.4f} p.u. ({v_max_global*400:.2f} V)",
                xy=(10.0, v_max_global), xytext=(35.0, v_max_global + 0.0006),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#08519c"),
                fontsize=7.5, color="#08519c", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#08519c", lw=0.5))

    ax.annotate(f"Mín global: {v_min_global:.4f} p.u. ({v_min_global*400:.2f} V)",
                xy=(130.0, v_min_global), xytext=(150.0, v_min_global - 0.0007),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#cb181d"),
                fontsize=7.5, color="#cb181d", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#cb181d", lw=0.5))

    secax = ax.secondary_yaxis('right', functions=(lambda x: x * 400.0, lambda x: x / 400.0))
    secax.set_ylabel(r"Tensión fase-fase $V_{\mathrm{LL}}$ [V]")
    secax.yaxis.set_major_locator(ticker.MultipleLocator(0.5))

    ax.set_xlabel("Tiempo $t$ [s]")
    ax.set_ylabel("Tensión nodal $V$ [p.u.]")
    ax.set_title("1. Perfil de Tensiones Nodales en el Tiempo (Nodos 1 a 8) — ESC-HIL-010 (660 s)", fontweight="bold")
    ax.set_xlim(-5, 665)
    ax.set_ylim(0.9990, 1.0045)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(50))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(0.001))
    ax.grid(True)
    ax.legend(loc="upper right", framealpha=0.92, ncol=3, fontsize=7.0)

    ax.text(0.02, 0.05, "Banda normativa IEEE 1547 / NTC 1340: [0.95, 1.05] p.u. (variación < 0.35%)",
            transform=ax.transAxes, fontsize=7.2, style="italic", color="#252525",
            bbox=dict(boxstyle="square,pad=0.2", facecolor="#ffffff", alpha=0.9, edgecolor="#cccccc", lw=0.5))

    save_figure(fig, "fig_1_perfil_tension_nodos_010", output_dirs)
    plt.close(fig)


# -----------------------------------------------------------------------------
# 2. PERFIL DE RADIACIÓN POA (ESC-HIL-010)
# -----------------------------------------------------------------------------
def plot_poa_010(df_meteo, output_dirs):
    fig, ax = plt.subplots(figsize=(FIG_WIDTH, 3.8))
    t = df_meteo["tiempo_s"].values
    poa = df_meteo["N2_POA_W_m2"].values

    add_event_spans_010(ax)

    ax.plot(t, poa, color="#d95f02", linewidth=1.5, label=r"Irradiancia en plano $G_{\mathrm{poa}}(t)$ [W/m²]", zorder=3)

    ax.annotate("Base nominal: 833.3 W/m²\n(Horario 10:00 AM)",
                xy=(100.0, 833.3), xytext=(50.0, 720.0),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#252525"),
                fontsize=7.5, color="#252525",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#cccccc", lw=0.5))

    ax.annotate("Sombreado suave (210–290 s)\nRampa 833 → 560 W/m² (-32.8%)",
                xy=(255.0, 560.0), xytext=(210.0, 420.0),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#a63603"),
                fontsize=7.5, color="#a63603",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#a63603", lw=0.5))

    ax.annotate("Sombreado abrupto (320–400 s)\nPartición R-E: 833 → 347 W/m² (-58.3%)",
                xy=(345.0, 347.0), xytext=(320.0, 200.0),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#cb181d"),
                fontsize=7.5, color="#cb181d",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#cb181d", lw=0.5))

    ax.annotate("Recuperación R-E\nCadena geométrica\n(370 a 400 s)",
                xy=(395.0, 833.3), xytext=(410.0, 680.0),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#2ca02c"),
                fontsize=7.5, color="#2ca02c",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#2ca02c", lw=0.5))

    ax.set_xlabel("Tiempo $t$ [s]")
    ax.set_ylabel(r"Irradiancia en plano $G_{\mathrm{poa}}$ [W/m²]")
    ax.set_title("2. Perfil de Radiación Solar POA — ESC-HIL-010 (660 s / Cumplimiento Regla R-E)", fontweight="bold")
    ax.set_xlim(-5, 665)
    ax.set_ylim(150, 950)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(50))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(100))
    ax.grid(True)
    ax.legend(loc="upper right", framealpha=0.92, fontsize=7.8)

    save_figure(fig, "fig_2_perfil_radiacion_poa_010", output_dirs)
    plt.close(fig)


# -----------------------------------------------------------------------------
# 3. FRECUENCIA DEL SISTEMA (ESC-HIL-010)
# -----------------------------------------------------------------------------
def plot_frequency_010(df_telem, output_dirs):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(FIG_WIDTH, 5.0), gridspec_kw={"height_ratios": [2.5, 1.2]}, sharex=True)

    t = df_telem["time_s"].values
    f = df_telem["f_sys_hz"].values
    p_net = df_telem["P_net_kW"].values

    # Subplot 1: Frecuencia
    add_event_spans_010(ax1)
    ax1.axhspan(59.95, 60.05, color="#2ca25f", alpha=0.20, label=r"Banda estrecha $\pm 0.05$ Hz (Meta)", zorder=1)
    ax1.axhspan(59.90, 60.10, color="#74c476", alpha=0.10, label=r"Banda IEEE 1547 $\pm 0.10$ Hz", zorder=1)
    ax1.axhline(60.0, color="#252525", linestyle="--", linewidth=0.9, alpha=0.8, label="Nominal 60.00 Hz")

    ax1.plot(t, f, color="#08519c", linewidth=1.1, label=r"Frecuencia medida $f_{\mathrm{sys}}(t)$", zorder=4)

    f_min, f_max = f.min(), f.max()
    t_min = t[np.argmin(f)]
    t_max = t[np.argmax(f)]

    ax1.annotate(f"Pico: {f_max:.3f} Hz (t={t_max:.1f} s)",
                 xy=(t_max, f_max), xytext=(t_max + 15, min(60.75, f_max + 0.08)),
                 arrowprops=dict(arrowstyle="->", lw=0.7, color="#08519c"),
                 fontsize=7.2, color="#08519c", fontweight="bold",
                 bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#08519c", lw=0.5))

    ax1.annotate(f"Valle: {f_min:.3f} Hz (t={t_min:.1f} s)",
                 xy=(t_min, f_min), xytext=(t_min + 15, max(59.35, f_min - 0.15)),
                 arrowprops=dict(arrowstyle="->", lw=0.7, color="#cb181d"),
                 fontsize=7.2, color="#cb181d", fontweight="bold",
                 bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#cb181d", lw=0.5))

    ax1.set_ylabel(r"Frecuencia $f_{\mathrm{sys}}$ [Hz]")
    ax1.set_title("3. Frecuencia del Sistema y Desbalance Neto — ESC-HIL-010 (660 s / Dinámica Estabilizada)", fontweight="bold")
    ax1.set_ylim(59.25, 60.85)
    ax1.yaxis.set_major_locator(ticker.MultipleLocator(0.2))
    ax1.grid(True)
    ax1.legend(loc="lower left", framealpha=0.92, ncol=2, fontsize=7.2)

    # Subplot 2: Potencia Neta P_net (causante del desvío de frecuencia)
    add_event_spans_010(ax2)
    ax2.plot(t, p_net, color="#006d2c", linewidth=1.1, label=r"Desbalance neto $P_{\mathrm{net}}(t) = P_{\mathrm{gen}} - P_{\mathrm{carga}}$ [kW]", zorder=3)
    ax2.axhline(0.0, color="#252525", linestyle=":", linewidth=0.8)
    ax2.set_xlabel("Tiempo $t$ [s]")
    ax2.set_ylabel(r"$P_{\mathrm{net}}$ [kW]")
    ax2.set_xlim(-5, 665)
    ax2.set_ylim(-4.5, 5.0)
    ax2.xaxis.set_major_locator(ticker.MultipleLocator(50))
    ax2.yaxis.set_major_locator(ticker.MultipleLocator(2.0))
    ax2.grid(True)
    ax2.legend(loc="upper right", framealpha=0.92, fontsize=7.2)

    save_figure(fig, "fig_3_frecuencia_sistema_010", output_dirs)
    plt.close(fig)


# -----------------------------------------------------------------------------
# 4. PERFIL DE DEMANDAS Y DEMANDA NETA (ESC-HIL-010)
# -----------------------------------------------------------------------------
def plot_demands_010(df_telem, df_demand, output_dirs):
    fig, ax = plt.subplots(figsize=(FIG_WIDTH, 4.4))

    t = df_demand["tiempo_s"].values
    p4 = df_demand["N4_P_kW"].values
    p5 = df_demand["N5_P_kW"].values
    p6 = df_demand["N6_P_kW"].values
    p7 = df_demand["N7_P_kW"].values
    p8 = df_demand["N8_P_kW"].values

    p_load_total = p4 + p5 + p6 + p7 + p8
    p_solar = df_telem["P2_kW"].values
    p_demanda_neta = p_load_total - p_solar
    p_net_grid = df_telem["P_net_kW"].values

    add_event_spans_010(ax)

    # 1. Cargas individuales
    ax.plot(t, p4, color="#aec7e8", linestyle="-", linewidth=0.9, alpha=0.85, label="N4 (Residencial)")
    ax.plot(t, p5, color="#ffbb78", linestyle="-", linewidth=0.9, alpha=0.85, label="N5 (Comercial)")
    ax.plot(t, p6, color="#c5b0d5", linestyle="-", linewidth=0.9, alpha=0.85, label="N6 (Industrial)")
    ax.plot(t, p7, color="#f7b6d2", linestyle="-", linewidth=0.9, alpha=0.85, label="N7 (Residencial)")
    ax.plot(t, p8, color="#c7c7c7", linestyle="-", linewidth=0.9, alpha=0.85, label="N8 (Comercial)")

    # 2. Demanda total agregada
    ax.plot(t, p_load_total, color="#08519c", linestyle="-", linewidth=2.0, label=r"Demanda total $P_{\mathrm{carga, total}}(t)$", zorder=4)

    # 3. Demanda neta vista por la generación despachable (P_load - P_solar)
    ax.plot(t, p_demanda_neta, color="#7a0177", linestyle="--", linewidth=1.8, label=r"Demanda neta $P_{\mathrm{neta}}(t) = P_{\mathrm{carga}} - P_{\mathrm{PV}}$", zorder=4)

    # 4. Potencia Solar inyectada P_solar
    ax.plot(t, p_solar, color="#ff7f0e", linestyle="-.", linewidth=1.2, label=r"Solar $P_{\mathrm{PV}}(t)$ (con curtailment)", zorder=3)

    ax.axhline(0.0, color="#525252", linestyle=":", linewidth=0.8, alpha=0.6)

    ax.annotate("Rampa +30% carga (40–70 s)\nDemanda sube a ~6.5 kW",
                xy=(70.0, 6.45), xytext=(80.0, 7.8),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#08519c"),
                fontsize=7.2, color="#08519c",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#08519c", lw=0.5))

    ax.annotate("Escalón -30% carga (100 s)\nDemanda neta cae a ~0.4 kW",
                xy=(102.0, 0.4), xytext=(40.0, -1.5),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#7a0177"),
                fontsize=7.2, color="#7a0177",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#7a0177", lw=0.5))

    ax.annotate("Sombreado abrupto (320 s)\nDemanda neta salta a ~3.7 kW",
                xy=(322.0, 3.7), xytext=(260.0, 5.2),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#cb181d"),
                fontsize=7.2, color="#cb181d",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#cb181d", lw=0.5))

    ax.set_xlabel("Tiempo $t$ [s]")
    ax.set_ylabel("Potencia activa $P$ [kW]")
    ax.set_title("4. Demandas Nodal e Integrada, Solar y Demanda Neta — ESC-HIL-010 (660 s)", fontweight="bold")
    ax.set_xlim(-5, 665)
    ax.set_ylim(-2.5, 9.5)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(50))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(1.5))
    ax.grid(True)
    ax.legend(loc="upper right", framealpha=0.92, ncol=3, fontsize=7.0)

    save_figure(fig, "fig_4_perfil_demandas_y_demanda_neta_010", output_dirs)
    plt.close(fig)


# -----------------------------------------------------------------------------
# 5. FIGURA SATÉLITES: COMPARACIÓN 011a (SoC ALTO) vs 011b (SoC BAJO)
# -----------------------------------------------------------------------------
def plot_satellites(df_011a, df_011b, output_dirs):
    fig, axes = plt.subplots(2, 2, figsize=(FIG_WIDTH, 5.2), sharex=True)

    t_a = df_011a["time_s"].values
    t_b = df_011b["time_s"].values

    # Columna Izquierda: Satélite 011a (SoC = 0.93 - Derating de Carga)
    # 1. Frecuencia 011a
    axes[0, 0].axhspan(59.95, 60.05, color="#2ca25f", alpha=0.2)
    axes[0, 0].axhline(60.0, color="#252525", linestyle="--", linewidth=0.8)
    axes[0, 0].plot(t_a, df_011a["f_sys_hz"].values, color="#08519c", linewidth=1.2, label=r"$f_{\mathrm{sys}}$ 011a")
    axes[0, 0].set_ylabel(r"$f_{\mathrm{sys}}$ [Hz]")
    axes[0, 0].set_title(r"ESC-HIL-011a ($\mathrm{SoC}_0 = 0.93$): Frecuencia", fontweight="bold", fontsize=8.5)
    axes[0, 0].set_ylim(59.4, 60.8)
    axes[0, 0].grid(True)
    axes[0, 0].annotate("Sobrefrecuencia sostenida\n(60.2 a 60.7 Hz tras evento t=30s)",
                        xy=(40.0, 60.6), xytext=(45.0, 60.2),
                        arrowprops=dict(arrowstyle="->", lw=0.7, color="#08519c"),
                        fontsize=6.8, color="#08519c", bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85))

    # 2. Potencias 011a
    axes[1, 0].plot(t_a, df_011a["P1_kW"].values, color="#1f77b4", linewidth=1.1, label=r"P1 Diésel")
    axes[1, 0].plot(t_a, df_011a["P2_kW"].values, color="#ff7f0e", linewidth=1.1, label=r"P2 Solar")
    axes[1, 0].plot(t_a, df_011a["P3_kW"].values, color="#9467bd", linewidth=1.3, label=r"P3 BESS (Carga)")
    axes[1, 0].plot(t_a, df_011a["P_net_kW"].values, color="#006d2c", linestyle=":", linewidth=1.0, label=r"P_net")
    axes[1, 0].axhline(0.0, color="#252525", linestyle="-", linewidth=0.6)
    axes[1, 0].set_xlabel("Tiempo $t$ [s]")
    axes[1, 0].set_ylabel("Potencia [kW]")
    axes[1, 0].set_title("011a: Despacho DER y Absorción BESS", fontweight="bold", fontsize=8.5)
    axes[1, 0].set_ylim(-3.5, 5.0)
    axes[1, 0].grid(True)
    axes[1, 0].legend(loc="upper right", framealpha=0.9, ncol=2, fontsize=6.8)

    # Columna Derecha: Satélite 011b (SoC = 0.22 - Derating de Descarga)
    # 3. Frecuencia 011b
    axes[0, 1].axhspan(59.95, 60.05, color="#2ca25f", alpha=0.2)
    axes[0, 1].axhline(60.0, color="#252525", linestyle="--", linewidth=0.8)
    axes[0, 1].plot(t_b, df_011b["f_sys_hz"].values, color="#2ca02c", linewidth=1.2, label=r"$f_{\mathrm{sys}}$ 011b")
    axes[0, 1].set_ylabel(r"$f_{\mathrm{sys}}$ [Hz]")
    axes[0, 1].set_title(r"ESC-HIL-011b ($\mathrm{SoC}_0 = 0.22$): Frecuencia", fontweight="bold", fontsize=8.5)
    axes[0, 1].set_ylim(59.4, 60.8)
    axes[0, 1].grid(True)
    axes[0, 1].annotate("Frecuencia regulada a 60.0 Hz\n(Diésel asume déficit en 5.2 kW)",
                        xy=(100.0, 60.0), xytext=(40.0, 59.55),
                        arrowprops=dict(arrowstyle="->", lw=0.7, color="#2ca02c"),
                        fontsize=6.8, color="#2ca02c", bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85))

    # 4. Potencias 011b
    axes[1, 1].plot(t_b, df_011b["P1_kW"].values, color="#1f77b4", linewidth=1.1, label=r"P1 Diésel")
    axes[1, 1].plot(t_b, df_011b["P2_kW"].values, color="#ff7f0e", linewidth=1.1, label=r"P2 Solar")
    axes[1, 1].plot(t_b, df_011b["P3_kW"].values, color="#9467bd", linewidth=1.3, label=r"P3 BESS (Descarga)")
    axes[1, 1].plot(t_b, df_011b["P_net_kW"].values, color="#006d2c", linestyle=":", linewidth=1.0, label=r"P_net")
    axes[1, 1].axhline(0.0, color="#252525", linestyle="-", linewidth=0.6)
    axes[1, 1].set_xlabel("Tiempo $t$ [s]")
    axes[1, 1].set_ylabel("Potencia [kW]")
    axes[1, 1].set_title("011b: Despacho DER y Derating Descarga BESS", fontweight="bold", fontsize=8.5)
    axes[1, 1].set_ylim(-1.0, 7.0)
    axes[1, 1].grid(True)
    axes[1, 1].legend(loc="upper right", framealpha=0.9, ncol=2, fontsize=6.8)

    save_figure(fig, "fig_5_satelites_frecuencia_y_derating", output_dirs)
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
    import json
    root = "D:/Antigravity/Projects/Tesis_Grado"
    
    # 1. Resolver telemetría de 010 desde CURRENT.json
    cur_010_path = os.path.join(root, "outputs/validation_v2/results/CURRENT.json")
    if os.path.exists(cur_010_path):
        with open(cur_010_path, "r", encoding="utf-8") as f:
            cur_data = json.load(f)
            telem_010 = cur_data["telemetry_path"]
            run_010_dir = cur_data["results_dir"]
    else:
        run_010_dir = os.path.join(root, "outputs/validation_v2/results/20261114T190831_ESC-HIL-010_validacion_integrada_v2_seed42")
        telem_010 = os.path.join(run_010_dir, "telemetry_rack.csv")

    meteo_010 = os.path.join(root, "Forms/escenarios_generados/ESC-HIL-010_validacion_integrada_v2/datos_meteorologicos.csv")
    demand_010 = os.path.join(root, "Forms/escenarios_generados/ESC-HIL-010_validacion_integrada_v2/datos_demanda.csv")

    # 2. Resolver satélites más recientes
    sat_base = os.path.join(root, "outputs/satellites/results")
    sat_entries = sorted(os.listdir(sat_base)) if os.path.exists(sat_base) else []
    runs_011a = [r for r in sat_entries if "011a" in r]
    runs_011b = [r for r in sat_entries if "011b" in r]

    dir_011a = os.path.join(sat_base, runs_011a[-1]) if runs_011a else os.path.join(sat_base, "20261114T112216_ESC-HIL-011a_soc_alto_seed42")
    dir_011b = os.path.join(sat_base, runs_011b[-1]) if runs_011b else os.path.join(sat_base, "20261114T112536_ESC-HIL-011b_soc_bajo_seed42")

    telem_011a = os.path.join(dir_011a, "telemetry_rack.csv")
    telem_011b = os.path.join(dir_011b, "telemetry_rack.csv")

    artifact_dir = "C:/Users/Jhonathan/.gemini/antigravity/brain/359a9c5f-f235-47d1-8ddc-d4f617f1081d"

    output_dirs = [
        os.path.join(root, "outputs/validation_v2/figures"),
        os.path.join(run_010_dir, "figures"),
        "D:/TEXTOS/TESIS/Figuras/validacion_v2",
        artifact_dir
    ]

    print("Cargando telemetrías y archivos de escenario...")
    print(f" - Telemetría 010:   {telem_010}")
    print(f" - Telemetría 011a:  {telem_011a}")
    print(f" - Telemetría 011b:  {telem_011b}")
    df_telem_010 = pd.read_csv(telem_010)
    df_meteo_010 = pd.read_csv(meteo_010)
    df_demand_010 = pd.read_csv(demand_010)

    df_011a = pd.read_csv(telem_011a)
    df_011b = pd.read_csv(telem_011b)

    print("\n[1/5] Generando Figura 1: Tensiones Nodales ESC-HIL-010...")
    plot_voltages_010(df_telem_010, output_dirs)

    print("\n[2/5] Generando Figura 2: Radiación Solar POA ESC-HIL-010...")
    plot_poa_010(df_meteo_010, output_dirs)

    print("\n[3/5] Generando Figura 3: Frecuencia del Sistema ESC-HIL-010...")
    plot_frequency_010(df_telem_010, output_dirs)

    print("\n[4/5] Generando Figura 4: Demandas y Demanda Neta ESC-HIL-010...")
    plot_demands_010(df_telem_010, df_demand_010, output_dirs)

    print("\n[5/5] Generando Figura 5: Dinámica de Satélites 011a vs 011b...")
    plot_satellites(df_011a, df_011b, output_dirs)

    print("\n[COMPLETADO] Todas las figuras han sido generadas y sincronizadas exitosamente.")

if __name__ == "__main__":
    main()
