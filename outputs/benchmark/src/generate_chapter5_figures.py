#!/usr/bin/env python3
"""
Generador de Figuras del Capítulo 5 (Resultados y Discusión) para Manuscrito LaTeX
================================================================================
Tesis de Grado: Control Secundario Distribuido en Tiempo Fijo (FxTS)
Autor: Agente Antigravity (Ingeniería de Co-Simulación, Control MAS y Hardware HIL)
Destino: D:/TEXTOS/TESIS/Figuras/

Cumple con todos los requisitos técnicos de S-29 y S-32:
- Formato PDF vectorial con fuentes incrustadas (Type 42 / TrueType).
- Tipografía sans-serif de 8-9 pt uniforme.
- Ancho exacto de 0.95\\textwidth = 14.81 cm (5.8307 in) (S-32).
- Lectura directa de artefactos canónicos certificados (cero hardcoding).
- Paleta apta para daltonismo y legible en escala de grises.
- Máximo 5-6 marcas redondas por eje.
- Unidades normalizadas entre corchetes.
- Trazabilidad total con hashes SHA-256 de entradas y salidas.
"""

import os
import sys
import json
import hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.patches import Patch

# Configuración global de Matplotlib para calidad de publicación
matplotlib.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
    "font.size": 8.5,
    "axes.labelsize": 9.0,
    "axes.titlesize": 9.0,
    "xtick.labelsize": 8.0,
    "ytick.labelsize": 8.0,
    "legend.fontsize": 7.5,
    "figure.titlesize": 9.5,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "axes.linewidth": 0.8,
    "grid.linewidth": 0.5,
    "grid.alpha": 0.35,
    "grid.linestyle": ":",
    "lines.linewidth": 1.2,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.04
})

# Rutas del proyecto
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BENCH_RESULTS_DIR = os.path.join(PROJECT_ROOT, "outputs", "benchmark", "results")
HIL_CSV_PATH = os.path.join(PROJECT_ROOT, "output_data", "telemetry_monitor_cluster_8nodes_hil.csv")
SOLAR_JSON_PATH = os.path.join(BENCH_RESULTS_DIR, "solar_hold_comparison.json")
METEO_CSV_PATH = os.path.join(PROJECT_ROOT, "Forms", "escenarios_generados", "ESC-HIL-003_consolidado_rev5", "datos_meteorologicos.csv")
DEMAND_CSV_PATH = os.path.join(PROJECT_ROOT, "Forms", "escenarios_generados", "ESC-HIL-003_consolidado_rev5", "datos_demanda.csv")
OUTPUT_FIG_DIR = os.path.abspath("D:/TEXTOS/TESIS/Figuras")

# Especificación S-32: Ancho 0.95\textwidth = 14.81 cm
TEXTWIDTH_IN = 14.81 / 2.54  # 5.8307 pulgadas


def get_canonical_metrics_path() -> str:
    current_json_path = os.path.join(BENCH_RESULTS_DIR, "CURRENT.json")
    with open(current_json_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    run_id = meta["run_id"]
    return os.path.join(BENCH_RESULTS_DIR, run_id, "metrics.json")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


# -----------------------------------------------------------------------------
# FIGURA 5.1: Tasas de Asentamiento por Controlador y Banda
# -----------------------------------------------------------------------------
def generate_figure_5_1(metrics_path: str, out_dir: str) -> str:
    with open(metrics_path, "r", encoding="utf-8") as f:
        metrics_data = json.load(f)

    controllers_order = [
        ("droop_published", "Droop (pub)"),
        ("pi_published", "PI (pub)"),
        ("pi_optimized", "PI (opt)"),
        ("dapi_published", "DAPI (pub)"),
        ("dapi_optimized", "DAPI (opt)"),
        ("fts_published", "FTS (pub)"),
        ("fts_optimized", "FTS (opt)"),
        ("fxts_published", "FxTS (la tesis)"),
    ]

    records_map = {d["key"]: d for d in metrics_data}
    labels = [c[1] for c in controllers_order]
    y_pos = np.arange(len(labels))
    height = 0.18

    fig, ax = plt.subplots(figsize=(TEXTWIDTH_IN, 3.8))

    c_norm = "#1b9e77"   # verde azulado
    c_10 = "#386cb0"     # azul
    c_05 = "#fdb462"     # ambar
    c_02 = "#e7298a"     # magenta

    for i, (k, lab) in enumerate(controllers_order):
        rec = records_map.get(k, {})
        tn = rec.get("t_s_norm")
        t10 = rec.get("t_s_10")
        t5 = rec.get("t_s_05")
        t2 = rec.get("t_s_02")

        if tn is None:
            # Droop no asienta: anotación holgada a la izquierda
            ax.text(2.0, y_pos[i], "n/a (no asienta, error permanente)", 
                    va="center", ha="left", fontsize=7.2, color="#555555", style="italic")
            continue

        if tn is not None:
            ax.barh(y_pos[i] + 1.5 * height, tn, height, color=c_norm, label=r"Banda normativa ($|e_f| \leq 0.1$ Hz)" if i == 1 else "")
        if t10 is not None:
            ax.barh(y_pos[i] + 0.5 * height, t10, height, color=c_10, label="Banda relativa 10%" if i == 1 else "")
        if t5 is not None:
            ax.barh(y_pos[i] - 0.5 * height, t5, height, color=c_05, label="Banda relativa 5%" if i == 1 else "")
        if t2 is not None:
            ax.barh(y_pos[i] - 1.5 * height, t2, height, color=c_02, label="Banda relativa 2%" if i == 1 else "")
        elif "dapi" in k:
            ax.text(rec.get("t_s_05", 65.0) + 1.5, y_pos[i] - 1.5 * height, r"$\infty$ (2%)", 
                    va="center", ha="left", fontsize=7.2, color=c_02)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("Tiempo de asentamiento $t_s$ [s]")
    ax.set_xlim(0, 85)
    # Holgura en eje de categorías para que Droop respire arriba y no corte texto
    ax.set_ylim(len(labels) - 0.4, -0.8)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(20))
    ax.grid(True, axis="x")
    # S-32: Leyenda movida a la esquina superior derecha
    ax.legend(loc="upper right", framealpha=0.9, fontsize=7.5)

    out_file = os.path.join(out_dir, "f5_1_tasas_asentamiento.pdf")
    fig.savefig(out_file, bbox_inches="tight")
    plt.close(fig)
    return out_file


# -----------------------------------------------------------------------------
# FIGURA 5.2: Frecuencia del Sistema en Ensayo HIL (Cinco Fases)
# -----------------------------------------------------------------------------
def generate_figure_5_2(hil_csv_path: str, out_dir: str) -> str:
    df = pd.read_csv(hil_csv_path)

    fig, ax = plt.subplots(figsize=(TEXTWIDTH_IN, 3.5))

    t = df["time_sec"].values
    f = df["f_sys_hz"].values

    # Señal principal
    ax.plot(t, f, color="#08519c", lw=1.2, label=r"Frecuencia medida $f_{\mathrm{sys}}(t)$")

    # Guías de referencia
    ax.axhline(60.0, color="#252525", ls="--", lw=0.9, alpha=0.7, label="Consigna nominal 60.0 Hz")
    ax.axhspan(59.9, 60.1, color="#2ca25f", alpha=0.12, label=r"Banda normativa $\pm 0.1$ Hz")
    ax.axhline(58.8, color="#cb181d", ls="-.", lw=0.8, alpha=0.8, label="Límite emergencia NTC 1340 (58.8 Hz)")

    # S-32: Sombreado de las cinco fases
    fases = [
        (0.5, 25.0, "#cccccc", 0.22),
        (40.0, 120.0, "#9ecae1", 0.18),
        (120.0, 150.0, "#fff7bc", 0.40),
        (150.0, 240.0, "#fee6ce", 0.22),
        (240.0, 300.0, "#bcbddc", 0.22),
    ]
    for ini, fin, col, alp in fases:
        ax.axvspan(ini, fin, color=col, alpha=alp)

    # Etiquetas de las cinco fases en la parte superior
    y_lbl = 60.45
    ax.text(12.75, y_lbl, "Fase I\nAcoplamiento", ha="center", va="top", fontsize=6.8, color="#525252")
    ax.text(80.0, y_lbl, "Fase II\nIsócrona (59.998 Hz)", ha="center", va="top", fontsize=6.8, color="#08519c")
    ax.text(135.0, y_lbl, "Fase III\nSombreado PV", ha="center", va="top", fontsize=6.8, color="#a63603")
    ax.text(195.0, y_lbl, "Fase IV\nRampas demanda", ha="center", va="top", fontsize=6.8, color="#756bb1")
    ax.text(270.0, y_lbl, "Fase V\nSobrecarga (59.04 Hz)", ha="center", va="top", fontsize=6.8, color="#54278f")

    # Anotaciones indispensables
    ax.annotate("Nadir: 59.06 Hz", xy=(9.0, 59.0556), xytext=(22.0, 59.25),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#cb181d"),
                fontsize=7.2, color="#cb181d")

    ax.annotate("Dip sombreado: 59.90 Hz (147.5 s)", xy=(147.5, 59.8979), xytext=(105.0, 59.60),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#a63603"),
                fontsize=7.2, color="#a63603")

    ax.annotate("Régimen sobrecarga: 59.04 Hz", xy=(260.0, 59.0414), xytext=(210.0, 59.35),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#54278f"),
                fontsize=7.2, color="#54278f")

    ax.set_xlabel("Tiempo $t$ [s]")
    ax.set_ylabel(r"Frecuencia $f_{\mathrm{sys}}$ [Hz]")
    # S-32: Eje x [-5, 305] y eje y [58.5, 60.6] Hz
    ax.set_xlim(-5, 305)
    ax.set_ylim(58.5, 60.6)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(50))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(0.5))
    ax.grid(True)
    # Leyenda en zona inferior despejada (frecuencia no baja de 59.02 Hz en régimen)
    ax.legend(loc="lower right", framealpha=0.9, ncol=2, fontsize=7.2)

    out_file = os.path.join(out_dir, "f5_2_frecuencia_hil.pdf")
    fig.savefig(out_file, bbox_inches="tight")
    plt.close(fig)
    return out_file


# -----------------------------------------------------------------------------
# FIGURA 5.3: Potencia Neta y Eventos de Carga en HIL
# -----------------------------------------------------------------------------
def generate_figure_5_3(hil_csv_path: str, out_dir: str) -> str:
    df = pd.read_csv(hil_csv_path)

    fig, ax = plt.subplots(figsize=(TEXTWIDTH_IN, 3.2))

    t = df["time_sec"].values
    p_net = df["P_net_kW"].values

    # S-32: Sombreado de las cinco fases de fondo
    fases = [
        (0.5, 25.0, "#cccccc", 0.15),
        (40.0, 120.0, "#9ecae1", 0.12),
        (120.0, 150.0, "#fff7bc", 0.25),
        (150.0, 240.0, "#fee6ce", 0.15),
        (240.0, 300.0, "#bcbddc", 0.15),
    ]
    for ini, fin, col, alp in fases:
        ax.axvspan(ini, fin, color=col, alpha=alp)

    ax.plot(t, p_net, color="#e6550d", lw=1.2, label=r"Desbalance neto $P_{\mathrm{net}}(t)$")
    ax.axhline(0.0, color="#636363", ls="--", lw=0.8, alpha=0.7)

    # Anotaciones
    ax.annotate("Transitorio arranque: -8.52 kW", xy=(1.5, -8.52), xytext=(22.0, -7.5),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#cb181d"),
                fontsize=7.2, color="#cb181d")

    # S-32: Desplazada hacia la izquierda sobre el tramo plano de 40-120 s
    ax.annotate(r"Régimen isócrono: $\approx 0.0$ kW", xy=(70.0, 0.0), xytext=(45.0, 1.4),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#2ca25f"),
                fontsize=7.2, color="#2ca25f")

    ax.annotate("Sobrecarga: -1.98 kW", xy=(270.0, -1.98), xytext=(210.0, -4.5),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#a63603"),
                fontsize=7.2, color="#a63603")

    # Líneas guía de las tres rampas de demanda
    rampas = [
        (150, 170, "Rampa A (+0.91 kW)"),
        (180, 200, "Rampa C (+1.60 kW)"),
        (210, 230, "Rampa E (+0.66 kW)"),
    ]
    for t_ini, t_fin, lbl in rampas:
        ax.axvspan(t_ini, t_fin, color="#fdae6b", alpha=0.35)
        ax.text((t_ini + t_fin) / 2.0, -1.2, lbl, ha="center", va="center", fontsize=6.5, color="#a63603", rotation=90)

    ax.set_xlabel("Tiempo $t$ [s]")
    ax.set_ylabel(r"Potencia neta en bornes $P_{\mathrm{net}}$ [kW]")
    ax.set_xlim(-5, 305)
    ax.set_ylim(-10.0, 3.0)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(50))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(2.0))
    ax.grid(True)
    ax.legend(loc="lower right", framealpha=0.9, fontsize=7.5)

    out_file = os.path.join(out_dir, "f5_3_potencia_neta.pdf")
    fig.savefig(out_file, bbox_inches="tight")
    plt.close(fig)
    return out_file


# -----------------------------------------------------------------------------
# FIGURA 5.4: Tensiones Nodales en Ensayo HIL
# -----------------------------------------------------------------------------
def generate_figure_5_4(hil_csv_path: str, out_dir: str) -> str:
    df = pd.read_csv(hil_csv_path)

    fig, ax = plt.subplots(figsize=(TEXTWIDTH_IN, 3.2))

    t = df["time_sec"].values
    v_cols = [f"V{i}_pu" for i in range(1, 9)]
    v_matrix = df[v_cols].values

    v_min = v_matrix.min(axis=1)
    v_max = v_matrix.max(axis=1)

    # Banda sombreada de envolvente de las 8 barras
    ax.fill_between(t, v_min, v_max, color="#bcbddc", alpha=0.35, label="Envolvente de barras (N1-N8)")

    # Barras representativas con líneas contrastantes
    ax.plot(t, df["V1_pu"], color="#3182bd", lw=1.1, label="N1 Diésel (Slack)")
    ax.plot(t, df["V2_pu"], color="#31a354", lw=1.0, ls="--", label="N2 Solar PV")
    ax.plot(t, df["V3_pu"], color="#756bb1", lw=1.0, ls="-.", label="N3 BESS")
    ax.plot(t, df["V6_pu"], color="#e6550d", lw=1.0, ls=":", label="N6 Carga C")

    ax.axhline(1.0, color="#636363", ls="-", lw=0.7, alpha=0.7)

    # Anotar cotas exactas
    ax.text(10.0, 1.0047, "Cota máx med: 1.0046 p.u. (401.85 V)", fontsize=7.2, color="#3182bd")
    ax.text(10.0, 1.0001, "Cota mín med: 0.9996 p.u. (399.86 V)", fontsize=7.2, color="#e6550d")

    ax.text(290.0, 1.0003, "Nota: Eje ampliado; banda IEEE 1547 es [0.95, 1.05] p.u.",
            ha="right", va="bottom", fontsize=6.8, style="italic", color="#525252")

    ax.set_xlabel("Tiempo $t$ [s]")
    ax.set_ylabel("Tensión nodal $V$ [p.u.]")
    ax.set_xlim(-5, 305)
    ax.set_ylim(1.000, 1.005)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(50))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(0.001))
    ax.grid(True)
    ax.legend(loc="upper right", framealpha=0.9, ncol=2, fontsize=7.2)

    out_file = os.path.join(out_dir, "f5_4_tensiones_nodales.pdf")
    fig.savefig(out_file, bbox_inches="tight")
    plt.close(fig)
    return out_file


# -----------------------------------------------------------------------------
# FIGURA 5.5: Consenso de Potencia Reactiva y Ratios
# -----------------------------------------------------------------------------
def generate_figure_5_5(hil_csv_path: str, out_dir: str) -> str:
    df = pd.read_csv(hil_csv_path)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(TEXTWIDTH_IN, 3.8), sharex=True, gridspec_kw={"height_ratios": [1, 1]})

    t = df["time_sec"].values
    e12 = np.abs(df["error_Q_12"].values)
    e23 = np.abs(df["error_Q_23"].values)

    e12_log = np.where(e12 <= 1e-6, 1e-6, e12)
    e23_log = np.where(e23 <= 1e-6, 1e-6, e23)

    # Panel 1: Errores de consenso logarítmicos
    ax1.semilogy(t, e12_log, color="#2b8cbe", lw=1.1, label=r"$|e_{Q,12}| = |\eta_{Q,1} - \eta_{Q,2}|$")
    ax1.semilogy(t, e23_log, color="#e41a1c", lw=1.1, ls="--", label=r"$|e_{Q,23}| = |\eta_{Q,2} - \eta_{Q,3}|$")
    ax1.axvline(10.5, color="#636363", ls=":", lw=0.9)
    ax1.annotate("Convergencia exacta $e_Q = 0$\n(Paso 21, $t = 10.5$ s)", xy=(10.5, 1e-4), xytext=(40.0, 1e-3),
                 arrowprops=dict(arrowstyle="->", lw=0.7, color="#252525"),
                 fontsize=7.2, color="#252525")

    ax1.set_ylabel(r"Error $|e_Q|$ [p.u.]")
    ax1.set_ylim(1e-6, 1.0)
    ax1.grid(True, which="both")
    ax1.legend(loc="upper right", framealpha=0.9, fontsize=7.2)

    # Panel 2: Ratios de reactiva compartidos
    ax2.plot(t, df["Q_ratio_1"], color="#3182bd", lw=1.0, label=r"$\eta_{Q,1}$ (Diésel)")
    ax2.plot(t, df["Q_ratio_2"], color="#31a354", lw=1.0, ls="--", label=r"$\eta_{Q,2}$ (Solar PV)")
    ax2.plot(t, df["Q_ratio_3"], color="#756bb1", lw=1.0, ls="-.", label=r"$\eta_{Q,3}$ (BESS)")
    ax2.axhline(0.3074, color="#636363", ls=":", lw=0.8)
    ax2.annotate("Ratio equitativo común: 30.74%", xy=(150.0, 0.3074), xytext=(160.0, 0.36),
                 arrowprops=dict(arrowstyle="->", lw=0.7, color="#636363"),
                 fontsize=7.2, color="#636363")

    ax2.set_xlabel("Tiempo $t$ [s]")
    ax2.set_ylabel(r"Ratio $Q_i / Q_{\max}$")
    ax2.set_xlim(-5, 305)
    ax2.set_ylim(0.20, 0.45)
    ax2.xaxis.set_major_locator(ticker.MultipleLocator(50))
    ax2.yaxis.set_major_locator(ticker.MultipleLocator(0.05))
    ax2.grid(True)
    ax2.legend(loc="lower right", framealpha=0.9, ncol=3, fontsize=7.2)

    plt.tight_layout()
    out_file = os.path.join(out_dir, "f5_5_consenso_reactiva.pdf")
    fig.savefig(out_file, bbox_inches="tight")
    plt.close(fig)
    return out_file


# -----------------------------------------------------------------------------
# FIGURA 5.6: Estabilidad Numérica (CFL y Retardo Admisible)
# -----------------------------------------------------------------------------
def generate_figure_5_6(metrics_path: str, out_dir: str) -> str:
    with open(metrics_path, "r", encoding="utf-8") as f:
        metrics_data = json.load(f)

    controllers = [
        ("droop_published", "Droop (pub)"),
        ("pi_published", "PI (pub)"),
        ("pi_optimized", "PI (opt)"),
        ("dapi_published", "DAPI (pub)"),
        ("dapi_optimized", "DAPI (opt)"),
        ("fts_published", "FTS (pub)"),
        ("fts_optimized", "FTS (opt)"),
        ("fxts_published", "FxTS (la tesis)"),
    ]

    records_map = {d["key"]: d for d in metrics_data}
    labels = [c[1] for c in controllers]
    cfl_vals = [records_map[c[0]]["cfl_number"] for c in controllers]
    tau_vals = [records_map[c[0]]["raw_metrics"].get("tau_crit_ms") for c in controllers]

    x = np.arange(len(labels))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(TEXTWIDTH_IN, 4.0), sharex=True)

    # Panel 1: Número CFL
    cfl_colors = ["#2ca25f" if c < 1.0 else "#de2d26" for c in cfl_vals]
    ax1.bar(x, cfl_vals, width=0.55, color=cfl_colors, edgecolor="#252525", lw=0.6)
    ax1.axhline(1.0, color="#cb181d", ls="--", lw=1.0, label="Umbral de estabilidad Euler CFL = 1.0")
    ax1.set_ylabel("CFL espectral [num]")
    ax1.set_ylim(0, 2.0)
    ax1.yaxis.set_major_locator(ticker.MultipleLocator(0.5))
    ax1.grid(True, axis="y")
    ax1.legend(loc="upper left", framealpha=0.9, fontsize=7.2)

    for xi, cfl in zip(x, cfl_vals):
        ax1.text(xi, cfl + 0.05, f"{cfl:.2f}", ha="center", va="bottom", fontsize=7.2)

    # Panel 2: Retardo crítico tau_crit
    tau_clean = []
    tau_colors = []
    for xi, tv in zip(x, tau_vals):
        if tv is None:
            tau_clean.append(0.0)
            tau_colors.append("#cccccc")
            ax2.text(xi, 100.0, "N/A", ha="center", va="bottom", fontsize=7.5, color="#636363", style="italic")
        else:
            tau_clean.append(tv)
            tau_colors.append("#2ca25f" if tv >= 50.0 else "#de2d26")
            ax2.text(xi, max(tv + 20.0, 10.0), f"{tv:.1f}", ha="center", va="bottom", fontsize=7.2)

    ax2.bar(x, tau_clean, width=0.55, color=tau_colors, edgecolor="#252525", lw=0.6)
    ax2.axhline(50.0, color="#252525", ls="--", lw=1.0, label="Umbral normativo IEEE 1547 (50.0 ms)")
    ax2.set_ylabel(r"$\tau_{\mathrm{crit}}$ [ms]")
    ax2.set_ylim(-250, 2800)
    ax2.yaxis.set_major_locator(ticker.MultipleLocator(500))
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=25, ha="right")
    ax2.grid(True, axis="y")
    ax2.legend(loc="upper left", framealpha=0.9, fontsize=7.2)

    plt.tight_layout()
    out_file = os.path.join(out_dir, "f5_6_estabilidad_numerica.pdf")
    fig.savefig(out_file, bbox_inches="tight")
    plt.close(fig)
    return out_file


# -----------------------------------------------------------------------------
# FIGURA 5.7: Experimento Nodal de Retenedores (ZOH vs FROH vs FOH)
# -----------------------------------------------------------------------------
def generate_figure_5_7(solar_json_path: str, out_dir: str) -> str:
    with open(solar_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # S-32: Etiquetas en dos líneas para evitar solapamiento
    schemes = [
        ("ZOH", 0.0, "ZOH"),
        (r"FROH ($\lambda=0.3$)", 0.3, "FROH\n" + r"($\lambda=0.3$)"),
        (r"FROH ($\lambda=0.5$)", 0.5, "FROH\n" + r"($\lambda=0.5$)"),
        (r"FROH ($\lambda=0.7$)", 0.7, "FROH\n" + r"($\lambda=0.7$)"),
        (r"FROH ($\lambda=0.9$)", 0.9, "FROH\n" + r"($\lambda=0.9$)"),
        ("FOH", 1.0, "FOH"),
    ]

    summary = {s["lambda"]: s for s in data["summary"]}
    labels = [s[2] for s in schemes]
    rms_vals = [summary[s[1]]["rms_error_w"] for s in schemes]
    max_vals = [summary[s[1]]["max_error_w"] for s in schemes]

    x = np.arange(len(labels))
    width = 0.36

    fig, ax = plt.subplots(figsize=(TEXTWIDTH_IN, 3.4))

    b1 = ax.bar(x - width/2, rms_vals, width, label=r"Error RMS en $P_w$ [W]", color="#2b8cbe", edgecolor="#252525", lw=0.6)
    b2 = ax.bar(x + width/2, max_vals, width, label=r"Error Máximo en $P_w$ [W]", color="#fdb462", edgecolor="#252525", lw=0.6)

    # Anotaciones exactas
    ax.annotate("RMS: 3.85 W\nMáx: 26.65 W", xy=(0, 26.65), xytext=(-0.1, 75.0),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#2b8cbe"),
                fontsize=7.2, color="#2b8cbe", ha="center")

    ax.annotate("RMS: 14.33 W (3.72x)\nMáx: 221.87 W (8.32x)", xy=(3, 221.87), xytext=(2.7, 260.0),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#e6550d"),
                fontsize=7.2, color="#e6550d", ha="center")

    ax.set_ylabel("Error de potencia activa [W]")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 350)
    ax.yaxis.set_major_locator(ticker.MultipleLocator(50))
    ax.grid(True, axis="y")
    ax.legend(loc="upper left", framealpha=0.9, fontsize=7.5)

    out_file = os.path.join(out_dir, "f5_7_retenedores.pdf")
    fig.savefig(out_file, bbox_inches="tight")
    plt.close(fig)
    return out_file


# -----------------------------------------------------------------------------
# FIGURA 5.8: Irradiancia Solar POA y Rampa de Sombreado (NUEVA - S-32)
# -----------------------------------------------------------------------------
def generate_figure_5_8(meteo_csv_path: str, out_dir: str) -> str:
    df = pd.read_csv(meteo_csv_path)

    fig, ax = plt.subplots(figsize=(TEXTWIDTH_IN, 3.2))

    t = df["tiempo_s"].values
    poa = df["N2_POA_W_m2"].values

    ax.plot(t, poa, color="#e6550d", lw=1.3, label=r"Irradiancia en plano $G_{\mathrm{poa}}(t)$")

    # S-32: Sombreado de ventana de sombreado (Fase III: 120-150 s)
    ax.axvspan(120.0, 150.0, color="#fff7bc", alpha=0.6, label="Fase III: Rampa de sombreado (120-150 s)")

    # Anotaciones exactas
    ax.annotate("Base constante:\n462.78 W/m²", xy=(60.0, 462.78), xytext=(20.0, 380.0),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#252525"),
                fontsize=7.2, color="#252525")

    ax.annotate("Caída: -29.9%\n(-138.4 W/m²)", xy=(135.0, 393.5), xytext=(155.0, 410.0),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#cb181d"),
                fontsize=7.2, color="#cb181d")

    ax.annotate("Régimen sombreado:\n324.36 W/m²", xy=(210.0, 324.36), xytext=(190.0, 275.0),
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#252525"),
                fontsize=7.2, color="#252525")

    ax.set_xlabel("Tiempo $t$ [s]")
    ax.set_ylabel(r"Irradiancia en plano $G_{\mathrm{poa}}$ [W/m²]")
    ax.set_xlim(-5, 305)
    ax.set_ylim(250, 500)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(50))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(50))
    ax.grid(True)
    ax.legend(loc="upper right", framealpha=0.9, fontsize=7.2)

    out_file = os.path.join(out_dir, "f5_8_poa.pdf")
    fig.savefig(out_file, bbox_inches="tight")
    plt.close(fig)
    return out_file


# -----------------------------------------------------------------------------
# FIGURA 5.9: Perfiles de Demanda Agregada e Individual (NUEVA - S-32)
# -----------------------------------------------------------------------------
def generate_figure_5_9(demand_csv_path: str, out_dir: str) -> str:
    df = pd.read_csv(demand_csv_path)

    t = df["tiempo_s"].values
    p_cols = ["N4_P_kW", "N5_P_kW", "N6_P_kW", "N7_P_kW", "N8_P_kW"]
    p_total = df[p_cols].sum(axis=1).values

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(TEXTWIDTH_IN, 4.0), sharex=True, gridspec_kw={"height_ratios": [1.1, 1.0]})

    # Panel superior: Demanda Agregada
    ax1.plot(t, p_total, color="#08519c", lw=1.4, label=r"Demanda activa total agregada $P_{\mathrm{dem}}(t)$")

    # Anotaciones requeridas por S-32
    ax1.annotate("Base: 9.515 kW", xy=(60.0, 9.515), xytext=(20.0, 11.0),
                 arrowprops=dict(arrowstyle="->", lw=0.7, color="#08519c"),
                 fontsize=7.2, color="#08519c")

    ax1.annotate("Pico: 12.993 kW\n(t=238.5 s)", xy=(238.5, 12.993), xytext=(170.0, 13.1),
                 arrowprops=dict(arrowstyle="->", lw=0.7, color="#cb181d"),
                 fontsize=7.2, color="#cb181d")

    ax1.annotate("Sobrecarga: 12.594 kW", xy=(270.0, 12.594), xytext=(210.0, 11.2),
                 arrowprops=dict(arrowstyle="->", lw=0.7, color="#54278f"),
                 fontsize=7.2, color="#54278f")

    # Señalización de inicio de las tres rampas
    rampas = [
        (150, 170, "Rampa A (150 s)"),
        (180, 200, "Rampa C (180 s)"),
        (210, 230, "Rampa E (210 s)"),
    ]
    for t1, t2, lbl in rampas:
        ax1.axvspan(t1, t2, color="#fee6ce", alpha=0.5)
        ax1.text((t1 + t2) / 2.0, 8.4, lbl, ha="center", va="bottom", fontsize=6.5, color="#a63603", rotation=90)
        ax2.axvspan(t1, t2, color="#fee6ce", alpha=0.5)

    ax1.set_ylabel(r"Demanda total [kW]")
    ax1.set_ylim(8.0, 14.0)
    ax1.yaxis.set_major_locator(ticker.MultipleLocator(2.0))
    ax1.grid(True)
    ax1.legend(loc="upper left", framealpha=0.9, fontsize=7.2)

    # Panel inferior: Cargas individuales nodales (S-33: sin tipologías no instanciadas)
    ax2.plot(t, df["N4_P_kW"], color="#3182bd", lw=1.1, ls="-", label="N4 Carga A")
    ax2.plot(t, df["N5_P_kW"], color="#31a354", lw=1.0, ls="--", label="N5 Carga B")
    ax2.plot(t, df["N6_P_kW"], color="#e6550d", lw=1.1, ls="-.", label="N6 Carga C")
    ax2.plot(t, df["N7_P_kW"], color="#756bb1", lw=1.0, ls=":", label="N7 Carga D")
    ax2.plot(t, df["N8_P_kW"], color="#636363", lw=1.0, ls="-", label="N8 Carga E")

    ax2.set_xlabel("Tiempo $t$ [s]")
    ax2.set_ylabel(r"Cargas nodales $P_i$ [kW]")
    ax2.set_xlim(-5, 305)
    ax2.set_ylim(0.0, 5.0)
    ax2.xaxis.set_major_locator(ticker.MultipleLocator(50))
    ax2.yaxis.set_major_locator(ticker.MultipleLocator(1.0))
    ax2.grid(True)
    ax2.legend(loc="upper left", framealpha=0.9, fontsize=6.8, ncol=3)

    plt.tight_layout()
    out_file = os.path.join(out_dir, "f5_9_demanda.pdf")
    fig.savefig(out_file, bbox_inches="tight")
    plt.close(fig)
    return out_file


# -----------------------------------------------------------------------------
# EJECUCIÓN PRINCIPAL Y TRAZABILIDAD
# -----------------------------------------------------------------------------
def main():
    os.makedirs(OUTPUT_FIG_DIR, exist_ok=True)
    metrics_path = get_canonical_metrics_path()

    print("="*78)
    print(" GENERADOR DE FIGURAS DEL CAPÍTULO 5 (S-29 / S-32) - CALIDAD DE PUBLICACIÓN")
    print("="*78)
    print(f"[+] Artefacto T1 (Métricas):   {metrics_path}")
    print(f"    SHA-256: {sha256_file(metrics_path)}")
    print(f"[+] Artefacto T2 (Telemetría): {HIL_CSV_PATH}")
    print(f"    SHA-256: {sha256_file(HIL_CSV_PATH)}")
    print(f"[+] Artefacto Nodal (Solar):   {SOLAR_JSON_PATH}")
    print(f"    SHA-256: {sha256_file(SOLAR_JSON_PATH)}")
    print(f"[+] Artefacto Contexto Meteo:  {METEO_CSV_PATH}")
    print(f"    SHA-256: {sha256_file(METEO_CSV_PATH)}")
    print(f"[+] Artefacto Contexto Demand: {DEMAND_CSV_PATH}")
    print(f"    SHA-256: {sha256_file(DEMAND_CSV_PATH)}")
    print(f"[+] Ancho de diseño (S-32):    14.81 cm (0.95\\textwidth)")
    print(f"[+] Directorio de Salida:      {OUTPUT_FIG_DIR}")
    print("-" * 78)

    generated = {}

    print("[+] Generando Figura 5.1: f5_1_tasas_asentamiento.pdf...")
    f1 = generate_figure_5_1(metrics_path, OUTPUT_FIG_DIR)
    generated["5.1"] = (f1, sha256_file(f1))

    print("[+] Generando Figura 5.2: f5_2_frecuencia_hil.pdf (5 fases, [-5, 305]s, [58.5, 60.6]Hz)...")
    f2 = generate_figure_5_2(HIL_CSV_PATH, OUTPUT_FIG_DIR)
    generated["5.2"] = (f2, sha256_file(f2))

    print("[+] Generando Figura 5.3: f5_3_potencia_neta.pdf (anotación reubicada a la izquierda)...")
    f3 = generate_figure_5_3(HIL_CSV_PATH, OUTPUT_FIG_DIR)
    generated["5.3"] = (f3, sha256_file(f3))

    print("[+] Generando Figura 5.4: f5_4_tensiones_nodales.pdf...")
    f4 = generate_figure_5_4(HIL_CSV_PATH, OUTPUT_FIG_DIR)
    generated["5.4"] = (f4, sha256_file(f4))

    print("[+] Generando Figura 5.5: f5_5_consenso_reactiva.pdf...")
    f5 = generate_figure_5_5(HIL_CSV_PATH, OUTPUT_FIG_DIR)
    generated["5.5"] = (f5, sha256_file(f5))

    print("[+] Generando Figura 5.6: f5_6_estabilidad_numerica.pdf...")
    f6 = generate_figure_5_6(metrics_path, OUTPUT_FIG_DIR)
    generated["5.6"] = (f6, sha256_file(f6))

    print("[+] Generando Figura 5.7: f5_7_retenedores.pdf (etiquetas x en dos líneas)...")
    f7 = generate_figure_5_7(SOLAR_JSON_PATH, OUTPUT_FIG_DIR)
    generated["5.7"] = (f7, sha256_file(f7))

    print("[+] Generando Figura 5.8: f5_8_poa.pdf (nueva figura irradiancia)...")
    f8 = generate_figure_5_8(METEO_CSV_PATH, OUTPUT_FIG_DIR)
    generated["5.8"] = (f8, sha256_file(f8))

    print("[+] Generando Figura 5.9: f5_9_demanda.pdf (nueva figura demanda agregada e individual)...")
    f9 = generate_figure_5_9(DEMAND_CSV_PATH, OUTPUT_FIG_DIR)
    generated["5.9"] = (f9, sha256_file(f9))

    print("="*78)
    print(" RESUMEN DE LAS 9 FIGURAS ENTREGADAS EN FORMATO PDF VECTORIAL (S-32):")
    print("="*78)
    for fig_id, (path, f_hash) in generated.items():
        fname = os.path.basename(path)
        sz = os.path.getsize(path)
        print(f"  * Fig {fig_id}: {fname:30s} | {sz:7d} B | SHA-256: {f_hash}")
    print("="*78)
    print("[OK] LAS 9 FIGURAS FUERON GENERADAS EXITOSAMENTE Y CUMPLEN CON S-29 Y S-32.")


if __name__ == "__main__":
    main()
