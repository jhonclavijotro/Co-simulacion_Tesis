#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generador de Figuras de Validación para ESC-HIL-012 (S1: Diesel Nominal en Isla)
==============================================================================
Genera figuras vectoriales de publicación científica (PDF + PNG 300 DPI):
  1. fig_s1_frecuencia_y_recuperacion: Dinámica de frecuencia ante escalón +20%
  2. fig_s1_potencias_generacion_y_demanda: Balance P1 (Diésel) vs Demanda
  3. fig_s1_tensiones_nodales: Tensiones en barras N1..N8 en pu
  4. fig_s1_panel_consolidado: Panel multipanel de 3 gráficos resumen del ensayo
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# Estilo para publicación científica IEEE / Elsevier
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
    "lines.linewidth": 1.3,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.04
})

FIG_WIDTH = 7.2  # Pulgadas
DPI = 300

def save_fig(fig, base_name, output_dirs):
    for out_dir in output_dirs:
        os.makedirs(out_dir, exist_ok=True)
        pdf_path = os.path.join(out_dir, f"{base_name}.pdf")
        png_path = os.path.join(out_dir, f"{base_name}.png")
        fig.savefig(pdf_path, format="pdf", dpi=DPI)
        fig.savefig(png_path, format="png", dpi=DPI)
        print(f"[OK] Guardada: {pdf_path}")
        print(f"[OK] Guardada: {png_path}")

def plot_frequency(df, output_dirs):
    fig, ax = plt.subplots(figsize=(FIG_WIDTH, 3.6))
    t = df["time_s"].values
    f = df["f_sys_hz"].values

    # Zonas
    ax.axvspan(0, 40, color="#f0f0f0", alpha=0.4, label="Régimen Base (Carga Nominal)")
    ax.axvspan(40, 100, color="#fee8c8", alpha=0.4, label="Transitorio Post-Escalón (+20% Carga)")
    ax.axvspan(100, 120, color="#e5f5e0", alpha=0.4, label="Cola Limpia de Evaluación")

    # Bandas normativas
    ax.axhline(60.0, color="#252525", linestyle="--", linewidth=1.0, alpha=0.7, label="Nominal (60.0 Hz)")
    ax.axhline(60.05, color="#cb181d", linestyle=":", linewidth=0.9, alpha=0.7, label="Banda Operativa ±0.05 Hz")
    ax.axhline(59.95, color="#cb181d", linestyle=":", linewidth=0.9, alpha=0.7)
    ax.axhline(60.10, color="#67000d", linestyle="-.", linewidth=0.8, alpha=0.5, label="Criterio 4 (±0.10 Hz)")
    ax.axhline(59.90, color="#67000d", linestyle="-.", linewidth=0.8, alpha=0.5)

    # Curva de frecuencia
    ax.plot(t, f, color="#1f77b4", linewidth=1.6, label="Frecuencia del Sistema $f(t)$")

    # Anotaciones
    f_nadir = np.min(f[t >= 40])
    t_nadir = t[t >= 40][np.argmin(f[t >= 40])]
    ax.annotate(f"Nadir: {f_nadir:.4f} Hz\n($t={t_nadir:.1f}$ s, $\\Delta f=-0.268$ Hz)",
                xy=(t_nadir, f_nadir), xytext=(t_nadir + 10, f_nadir - 0.08),
                arrowprops=dict(facecolor="#cb181d", shrink=0.08, width=1.0, headwidth=5),
                fontsize=8.0, fontweight="semibold", color="#cb181d",
                bbox=dict(boxstyle="round,pad=0.3", fc="#ffffff", ec="#cb181d", lw=0.8))

    # Anotación cola limpia
    f_tail = f[t >= 100]
    p2p_tail = np.ptp(f_tail)
    ax.annotate(f"Cola Limpia [100, 120] s:\n$f_{{mean}} = {np.mean(f_tail):.4f}$ Hz\n$p2p = {p2p_tail:.4f}$ Hz (PASS $\\leq 0.10$)",
                xy=(110, np.mean(f_tail)), xytext=(78, 60.04),
                arrowprops=dict(facecolor="#2ca02c", shrink=0.08, width=1.0, headwidth=5),
                fontsize=8.0, fontweight="semibold", color="#2ca02c",
                bbox=dict(boxstyle="round,pad=0.3", fc="#ffffff", ec="#2ca02c", lw=0.8))

    ax.set_xlabel("Tiempo [s]")
    ax.set_ylabel("Frecuencia [Hz]")
    ax.set_title("ESC-HIL-012 (S1) · Dinámica de Frecuencia ante Escalón de Demanda (+20% en $t=40$ s)")
    ax.set_xlim(0, 120)
    ax.set_ylim(59.50, 60.12)
    ax.grid(True)
    ax.legend(loc="lower right", framealpha=0.92, ncol=2)

    save_fig(fig, "fig_s1_frecuencia_y_recuperacion", output_dirs)
    plt.close(fig)

def plot_powers(df, output_dirs):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(FIG_WIDTH, 4.8), sharex=True, gridspec_kw={"height_ratios": [2.5, 1.2]})
    t = df["time_s"].values

    # Panel 1: Diésel y Demanda
    ax1.plot(t, df["P_load_total_kW"], color="#000000", linestyle="--", linewidth=1.5, label="Demanda Total $P_{load}$")
    ax1.plot(t, df["P1_kW"], color="#1f77b4", linewidth=1.6, label="Generación Diésel $P_1$ (N1 Slack)")
    ax1.axhline(3.5, color="#cb181d", linestyle=":", linewidth=1.0, alpha=0.8, label="Límite Técnico Inferior $P_{1,min}=3.5$ kW")
    ax1.axhline(10.0, color="#67000d", linestyle="-.", linewidth=1.0, alpha=0.8, label="Límite Máximo $P_{1,max}=10.0$ kW")

    ax1.set_ylabel("Potencia Activa [kW]")
    ax1.set_title("ESC-HIL-012 (S1) · Balance de Potencia Activa y Regulación Isócrona")
    ax1.set_ylim(2.5, 11.0)
    ax1.grid(True)
    ax1.legend(loc="upper left", framealpha=0.92, ncol=2)

    # Panel 2: DERs inactivos (Solar y BESS)
    ax2.plot(t, df["P2_kW"], color="#2ca02c", linewidth=1.4, label="Solar $P_2$ ($POA=0$ W/m²)")
    ax2.plot(t, df["P3_kW"], color="#9467bd", linewidth=1.4, label="BESS $P_3$ ($SoC_0=0.20$, Inerte)")
    ax2.set_xlabel("Tiempo [s]")
    ax2.set_ylabel("DERs [kW]")
    ax2.set_ylim(-0.2, 0.5)
    ax2.set_xlim(0, 120)
    ax2.grid(True)
    ax2.legend(loc="upper right", framealpha=0.92)

    save_fig(fig, "fig_s1_potencias_generacion_y_demanda", output_dirs)
    plt.close(fig)

def plot_voltages(df, output_dirs):
    fig, ax = plt.subplots(figsize=(FIG_WIDTH, 3.6))
    t = df["time_s"].values

    v_keys = [
        ("V1_pu", "#1f77b4", "-", 1.5, "N1: Diésel (Slack)"),
        ("V2_pu", "#2ca02c", "-", 1.2, "N2: Solar"),
        ("V3_pu", "#9467bd", "-", 1.2, "N3: BESS"),
        ("V4_pu", "#ff7f0e", "--", 1.0, "N4: Carga Residencial"),
        ("V5_pu", "#d62728", "--", 1.0, "N5: Carga Comercial"),
        ("V6_pu", "#8c564b", "-.", 1.0, "N6: Carga Industrial"),
        ("V7_pu", "#e377c2", ":", 1.0, "N7: Carga Residencial 2"),
        ("V8_pu", "#7f7f7f", ":", 1.0, "N8: Carga Comercial 2"),
    ]

    for key, color, ls, lw, lbl in v_keys:
        if key in df.columns:
            ax.plot(t, df[key], label=lbl, color=color, linestyle=ls, linewidth=lw)

    ax.axhline(1.05, color="#cb181d", linestyle="--", linewidth=0.9, alpha=0.6, label="Límite ANSI C84.1 (±5%)")
    ax.axhline(0.95, color="#cb181d", linestyle="--", linewidth=0.9, alpha=0.6)

    ax.set_xlabel("Tiempo [s]")
    ax.set_ylabel("Tensión [pu]")
    ax.set_title("ESC-HIL-012 (S1) · Perfil de Tensiones Nodales en Barras N1..N8")
    ax.set_xlim(0, 120)
    ax.set_ylim(0.995, 1.005)
    ax.grid(True)
    ax.legend(loc="lower right", framealpha=0.92, ncol=3)

    save_fig(fig, "fig_s1_tensiones_nodales", output_dirs)
    plt.close(fig)

def plot_consolidated(df, output_dirs):
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(FIG_WIDTH, 7.2), sharex=True)
    t = df["time_s"].values

    # 1. Frecuencia
    ax1.plot(t, df["f_sys_hz"], color="#1f77b4", linewidth=1.4)
    ax1.axhline(60.0, color="#252525", linestyle="--", alpha=0.6)
    ax1.axhline(60.05, color="#cb181d", linestyle=":", alpha=0.6)
    ax1.axhline(59.95, color="#cb181d", linestyle=":", alpha=0.6)
    ax1.set_ylabel("Frecuencia [Hz]")
    ax1.set_title("ESC-HIL-012 (S1) · Panel Consolidado de Validación: Diésel Nominal en Isla")
    ax1.set_ylim(59.50, 60.10)
    ax1.grid(True)

    # 2. Potencias
    ax2.plot(t, df["P_load_total_kW"], color="#000000", linestyle="--", linewidth=1.3, label="Demanda Total")
    ax2.plot(t, df["P1_kW"], color="#1f77b4", linewidth=1.4, label="Diésel P1")
    ax2.set_ylabel("Potencia [kW]")
    ax2.set_ylim(3.0, 9.0)
    ax2.grid(True)
    ax2.legend(loc="upper left")

    # 3. Tensiones
    for i in range(1, 9):
        col = f"V{i}_pu"
        if col in df.columns:
            ax3.plot(t, df[col], label=f"N{i}", linewidth=1.0)
    ax3.set_xlabel("Tiempo [s]")
    ax3.set_ylabel("Tensión [pu]")
    ax3.set_ylim(0.998, 1.004)
    ax3.set_xlim(0, 120)
    ax3.grid(True)
    ax3.legend(loc="lower right", ncol=4)

    save_fig(fig, "fig_s1_panel_consolidado", output_dirs)
    plt.close(fig)

def main():
    csv_path = "outputs/custom/results/20261114T204419_ESC-HIL-012_diesel_nominal_isla_seed42/telemetry_rack.csv"
    if not os.path.exists(csv_path):
        print(f"[ERROR] Archivo de telemetría no encontrado: {csv_path}")
        sys.exit(1)

    df = pd.read_csv(csv_path)

    run_dir = os.path.dirname(csv_path)
    output_dirs = [
        os.path.join(run_dir, "figures"),
        "outputs/custom/figures/S1_diesel",
        "D:/TEXTOS/TESIS/Figuras/escenarios_independientes/S1_diesel",
        "C:/Users/Jhonathan/.gemini/antigravity/brain/359a9c5f-f235-47d1-8ddc-d4f617f1081d"
    ]

    print(f"Generando figuras científicas para S1 desde {csv_path}...")
    plot_frequency(df, output_dirs)
    plot_powers(df, output_dirs)
    plot_voltages(df, output_dirs)
    plot_consolidated(df, output_dirs)
    print("\n[COMPLETADO] Figuras de S1 generadas exitosamente en todos los destinos.")

if __name__ == "__main__":
    main()
