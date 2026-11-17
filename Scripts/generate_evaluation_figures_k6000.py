#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generador de Figuras Comparativas para S2, S3 y ESC-HIL-010 con k_BESS = -6000 W/Hz
==================================================================================
Genera figuras vectoriales (PDF) y de alta resolución (PNG 300 DPI) para evaluar:
  1. Comparativa S2 (con espacio BESS) vs S3 (sin espacio BESS) con certificación p2p <= 0.10 Hz
  2. Dinámica completa de ESC-HIL-010 (Frecuencia, Potencias y Recorte Solar)
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

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

FIG_WIDTH = 7.2
DPI = 300

def save_fig(fig, base_name, out_dirs):
    for d in out_dirs:
        os.makedirs(d, exist_ok=True)
        pdf_path = os.path.join(d, f"{base_name}.pdf")
        png_path = os.path.join(d, f"{base_name}.png")
        fig.savefig(pdf_path, format="pdf", dpi=DPI)
        fig.savefig(png_path, format="png", dpi=DPI)
        print(f"[OK] Guardada: {pdf_path}")
        print(f"[OK] Guardada: {png_path}")

def plot_s2_s3_comparison(df_s2, df_s3, out_dirs):
    fig, axes = plt.subplots(3, 2, figsize=(FIG_WIDTH, 7.2), sharex=True)
    t2 = df_s2["time_s"].values
    t3 = df_s3["time_s"].values

    # Columna 1: S2 (ESC-HIL-013, SoC=0.50)
    ax_f2, ax_p2, ax_c2 = axes[0, 0], axes[1, 0], axes[2, 0]
    # Columna 2: S3 (ESC-HIL-014, SoC=0.95)
    ax_f3, ax_p3, ax_c3 = axes[0, 1], axes[1, 1], axes[2, 1]

    # --- S2: Frecuencia ---
    ax_f2.set_title("S2: Excedente con Espacio BESS ($SoC_0=0.50$)\n$k_{\\mathrm{BESS}}=-6000$ W/Hz — CERTIFICADO ($p2p=0.0929$ Hz)", fontweight="bold")
    ax_f2.axvspan(40, 100, color="#fee8c8", alpha=0.3, label="Escalón -15%")
    ax_f2.axvspan(100, 120, color="#e5f5e0", alpha=0.3, label="Cola Limpia ($p2p \\leq 0.10$)")
    ax_f2.axhline(60.0, color="#252525", linestyle="--", linewidth=0.8)
    ax_f2.axhline(60.05, color="#cb181d", linestyle=":", linewidth=0.8)
    ax_f2.axhline(59.95, color="#cb181d", linestyle=":", linewidth=0.8)
    ax_f2.plot(t2, df_s2["f_sys_hz"], color="#1f77b4", label="Frecuencia $f(t)$")
    ax_f2.set_ylabel("Frecuencia [Hz]")
    ax_f2.set_ylim(59.85, 60.15)
    ax_f2.grid(True)
    ax_f2.legend(loc="upper right", framealpha=0.8)

    # --- S2: Potencias ---
    ax_p2.axvspan(40, 100, color="#fee8c8", alpha=0.3)
    ax_p2.axvspan(100, 120, color="#e5f5e0", alpha=0.3)
    ax_p2.plot(t2, df_s2["P1_kW"], color="#2ca02c", label="$P_1$ Diésel")
    ax_p2.plot(t2, df_s2["P2_kW"], color="#ff7f0e", label="$P_2$ Solar")
    ax_p2.plot(t2, df_s2["P3_kW"], color="#9467bd", label="$P_3$ BESS")
    ax_p2.plot(t2, df_s2["P_load_total_kW"], color="#333333", linestyle="--", alpha=0.7, label="$P_{\\mathrm{demanda}}$")
    ax_p2.axhline(3.5, color="#d62728", linestyle=":", linewidth=0.8, label="$P_{\\mathrm{min}}$ Diésel (3.5 kW)")
    ax_p2.set_ylabel("Potencia [kW]")
    ax_p2.set_ylim(-1.0, 7.5)
    ax_p2.grid(True)
    ax_p2.legend(loc="upper right", ncol=2, framealpha=0.8)

    # --- S2: Absorción y Recorte ---
    ax_c2.axvspan(40, 100, color="#fee8c8", alpha=0.3)
    ax_c2.axvspan(100, 120, color="#e5f5e0", alpha=0.3)
    ax_c2.plot(t2, df_s2["P3_kW"], color="#9467bd", label="$P_3$ BESS (Absorción < 0)")
    ax_c2.plot(t2, df_s2["P_curtailed_kW"], color="#d62728", label="$P_{\\mathrm{curt}}$ Recorte Solar")
    ax_c2.set_ylabel("Potencia [kW]")
    ax_c2.set_xlabel("Tiempo [s]")
    ax_c2.set_ylim(-0.8, 1.2)
    ax_c2.grid(True)
    ax_c2.legend(loc="upper right", framealpha=0.8)

    # --- S3: Frecuencia ---
    ax_f3.set_title("S3: Excedente sin Espacio BESS ($SoC_0=0.95$)\n$k_{\\mathrm{BESS}}=-6000$ W/Hz — Recorte Solar Exclusivo", fontweight="bold")
    ax_f3.axvspan(40, 100, color="#fee8c8", alpha=0.3, label="Escalón -15%")
    ax_f3.axvspan(100, 120, color="#e5f5e0", alpha=0.3, label="Cola Limpia ($p2p=0.1469$)")
    ax_f3.axhline(60.0, color="#252525", linestyle="--", linewidth=0.8)
    ax_f3.axhline(60.05, color="#cb181d", linestyle=":", linewidth=0.8)
    ax_f3.axhline(59.95, color="#cb181d", linestyle=":", linewidth=0.8)
    ax_f3.plot(t3, df_s3["f_sys_hz"], color="#1f77b4", label="Frecuencia $f(t)$")
    ax_f3.set_ylabel("Frecuencia [Hz]")
    ax_f3.set_ylim(59.80, 60.20)
    ax_f3.grid(True)
    ax_f3.legend(loc="upper right", framealpha=0.8)

    # --- S3: Potencias ---
    ax_p3.axvspan(40, 100, color="#fee8c8", alpha=0.3)
    ax_p3.axvspan(100, 120, color="#e5f5e0", alpha=0.3)
    ax_p3.plot(t3, df_s3["P1_kW"], color="#2ca02c", label="$P_1$ Diésel")
    ax_p3.plot(t3, df_s3["P2_kW"], color="#ff7f0e", label="$P_2$ Solar")
    ax_p3.plot(t3, df_s3["P3_kW"], color="#9467bd", label="$P_3$ BESS")
    ax_p3.plot(t3, df_s3["P_load_total_kW"], color="#333333", linestyle="--", alpha=0.7, label="$P_{\\mathrm{demanda}}$")
    ax_p3.axhline(3.5, color="#d62728", linestyle=":", linewidth=0.8, label="$P_{\\mathrm{min}}$ Diésel (3.5 kW)")
    ax_p3.set_ylabel("Potencia [kW]")
    ax_p3.set_ylim(-1.0, 7.5)
    ax_p3.grid(True)
    ax_p3.legend(loc="upper right", ncol=2, framealpha=0.8)

    # --- S3: Absorción y Recorte ---
    ax_c3.axvspan(40, 100, color="#fee8c8", alpha=0.3)
    ax_c3.axvspan(100, 120, color="#e5f5e0", alpha=0.3)
    ax_c3.plot(t3, df_s3["P3_kW"], color="#9467bd", label="$P_3$ BESS (Bloqueado $\\geq 0$)")
    ax_c3.plot(t3, df_s3["P_curtailed_kW"], color="#d62728", label="$P_{\\mathrm{curt}}$ Recorte Solar")
    ax_c3.set_ylabel("Potencia [kW]")
    ax_c3.set_xlabel("Tiempo [s]")
    ax_c3.set_ylim(-0.4, 1.8)
    ax_c3.grid(True)
    ax_c3.legend(loc="upper right", framealpha=0.8)

    plt.tight_layout()
    save_fig(fig, "fig_comparativa_s2_s3_k6000", out_dirs)
    plt.close(fig)

def plot_010_overview(df_010, out_dirs):
    fig, (ax_f, ax_p, ax_c) = plt.subplots(3, 1, figsize=(FIG_WIDTH, 6.8), sharex=True)
    t = df_010["time_s"].values

    # Frecuencia
    ax_f.set_title("ESC-HIL-010_validacion_integrada_v2: Dinámica Global con $k_{\\mathrm{BESS}}=-6000$ W/Hz", fontweight="bold")
    ax_f.axhline(60.0, color="#252525", linestyle="--", linewidth=0.8)
    ax_f.axhline(60.05, color="#cb181d", linestyle=":", linewidth=0.8)
    ax_f.axhline(59.95, color="#cb181d", linestyle=":", linewidth=0.8)
    ax_f.axvspan(620, 660, color="#e5f5e0", alpha=0.4, label="Cola Limpia Final ($p2p=0.1154$ Hz)")
    ax_f.plot(t, df_010["f_sys_hz"], color="#1f77b4", label="Frecuencia $f(t)$")
    ax_f.set_ylabel("Frecuencia [Hz]")
    ax_f.set_ylim(59.6, 60.5)
    ax_f.grid(True)
    ax_f.legend(loc="upper right", framealpha=0.8)

    # Potencias
    ax_p.plot(t, df_010["P1_kW"], color="#2ca02c", label="$P_1$ Diésel")
    ax_p.plot(t, df_010["P2_kW"], color="#ff7f0e", label="$P_2$ Solar")
    ax_p.plot(t, df_010["P3_kW"], color="#9467bd", label="$P_3$ BESS")
    ax_p.plot(t, df_010["P_load_total_kW"], color="#333333", linestyle="--", alpha=0.7, label="$P_{\\mathrm{demanda}}$")
    ax_p.axhline(3.5, color="#d62728", linestyle=":", linewidth=0.8, label="$P_{\\mathrm{min}}$ Diésel")
    ax_p.set_ylabel("Potencia [kW]")
    ax_p.set_ylim(-1.5, 9.0)
    ax_p.grid(True)
    ax_p.legend(loc="upper right", ncol=3, framealpha=0.8)

    # Recorte Solar y BESS
    ax_c.plot(t, df_010["P_curtailed_kW"], color="#d62728", label="$P_{\\mathrm{curt}}$ Recorte Solar")
    ax_c.plot(t, df_010["curtail_ratio"] * 3.0, color="#ff7f0e", linestyle=":", label="Ratio Recorte $(\\times 3)$")
    ax_c.plot(t, df_010["P3_kW"], color="#9467bd", label="$P_3$ BESS (Iny > 0 / Abs < 0)")
    ax_c.set_ylabel("Recorte / BESS [kW]")
    ax_c.set_xlabel("Tiempo [s]")
    ax_c.set_ylim(-1.2, 3.2)
    ax_c.grid(True)
    ax_c.legend(loc="upper right", ncol=3, framealpha=0.8)

    plt.tight_layout()
    save_fig(fig, "fig_010_overview_k6000", out_dirs)
    plt.close(fig)

def main():
    p_s2 = "outputs/custom/results/20261117T080129_ESC-HIL-013_excedente_con_espacio_seed42/telemetry_rack.csv"
    p_s3 = "outputs/custom/results/20261117T080149_ESC-HIL-014_excedente_sin_espacio_seed42/telemetry_rack.csv"
    p_010 = "outputs/validation_v2/results/20261117T080205_ESC-HIL-010_validacion_integrada_v2_seed42/telemetry_rack.csv"

    brain_dir = os.environ.get("ARTIFACT_DIR", r"C:\Users\Jhonathan\.gemini\antigravity\brain\359a9c5f-f235-47d1-8ddc-d4f617f1081d")
    out_dirs = [brain_dir, "outputs/custom/figures_k6000"]

    if os.path.exists(p_s2) and os.path.exists(p_s3):
        print("[INFO] Generando comparativa S2 vs S3...")
        df2 = pd.read_csv(p_s2)
        df3 = pd.read_csv(p_s3)
        plot_s2_s3_comparison(df2, df3, out_dirs)

    if os.path.exists(p_010):
        print("[INFO] Generando visualización global ESC-HIL-010...")
        df010 = pd.read_csv(p_010)
        plot_010_overview(df010, out_dirs)

if __name__ == "__main__":
    main()
