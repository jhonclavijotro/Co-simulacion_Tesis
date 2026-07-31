"""Co-simulacion distribuida: 5 nodos, 1 hora sintetica.

Escenario:
  Nodo 0: Slack (110V)
  Nodo 1: BESS (PC, P_rated=5kW, SoC=50%)
  Nodo 2: Carga 1 (2000W, fp=0.95)
  Nodo 3: Solar (RPi, P_rated=3kW, perfil gaussiano)
  Nodo 4: Carga 2 (1500W, fp=0.95)

Modos:
  --local     : BESS + Solar corren en PC (prueba integral)
  --remoto    : BESS en PC, Solar en RPi via ZMQ
  --plot-only : solo regenera graficas desde CSV guardado
  --solo-server: solo el servidor (para probar con agente RPi externo)
"""

import argparse
import csv
import math
import os
import sys
import threading
import time as _time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from CentralPC.reloj_zmq import RelojZMQ
from CentralPC.master_clock import MasterClock
from MAS.BESS_simplificado import BateriaSimplificada
from Solar.SolarSimplificado import SolarSimplificado
from MAS.agente_zmq import AgenteZMQ


PASO_MAESTRO = 0.1
TIEMPO_TOTAL = 3600.0
N_AGENTES = 2
PUERTO_ZMQ = 5000
ARCHIVO_RED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "CentralPC", "red_5nodos.csv")

CARGAS = {
    2: (-2000.0, -657.0),
    4: (-1500.0, -493.0),
}

AGENTE_NODO = {1: 1, 2: 3}


def _loop_bess_agent(id_agente, host, puerto, SoC_inicial, capacidad_Ah,
                     P_rated, K_soc, paso):
    bess = BateriaSimplificada(
        V_nominal=48.0, capacidad_Ah=capacidad_Ah,
        SoC_inicial=SoC_inicial, N_serie=10,
    )
    zmq = AgenteZMQ(id_agente, host=host, puerto=puerto)
    zmq.conectar()
    print(f"[BESS:{id_agente}] Iniciando loop SoC={SoC_inicial:.4f} P_rated={P_rated:.0f}W")
    try:
        while True:
            tick = zmq.esperar_tick()
            if tick is None:
                break
            demanda_w = tick.get("demanda_w", 0)
            SoC_avg = tick.get("SoC_avg", bess.SoC)
            paso_num = tick.get("step", 0)
            num_agentes = tick.get("num_agentes", 1)
            fraccion = 1.0 / num_agentes if num_agentes > 0 else 1.0
            desvio = bess.SoC - SoC_avg
            fraccion += K_soc * desvio
            P_ref = demanda_w * fraccion
            P_ref = max(-P_rated, min(P_rated, P_ref))
            V_pcc_ag = tick.get("V_pcc", {}).get(str(id_agente))
            bess.step(paso, P_ref, V_pcc=V_pcc_ag)
            zmq.enviar_medicion(
                P_ref=P_ref, SoC=bess.SoC, cobertura=1,
                SoC_avg=SoC_avg, paso=paso_num,
            )
            if paso_num % 1000 == 0:
                print(f"  [BESS:{id_agente}] paso {paso_num} "
                      f"SoC={bess.SoC:.4f} P_ref={P_ref:.0f}W")
    except KeyboardInterrupt:
        pass
    zmq.desconectar()
    print(f"[BESS:{id_agente}] Finalizado")


def _loop_solar_agent(id_agente, host, puerto, P_rated, paso):
    solar = SolarSimplificado(P_rated=P_rated, T_total=TIEMPO_TOTAL)
    zmq = AgenteZMQ(id_agente, host=host, puerto=puerto)
    zmq.conectar()
    print(f"[Solar:{id_agente}] Iniciando loop P_rated={P_rated:.0f}W")
    try:
        while True:
            tick = zmq.esperar_tick()
            if tick is None:
                break
            paso_num = tick.get("step", 0)
            V_pcc_dict = tick.get("V_pcc", {})
            V_pcc_ag = V_pcc_dict.get(str(id_agente))
            solar.step(paso, 0.0, V_pcc=V_pcc_ag)
            zmq.enviar_medicion(
                P_ref=solar.P_real, SoC=solar.SoC, cobertura=1,
                SoC_avg=0.0, paso=paso_num,
            )
            if paso_num % 1000 == 0:
                print(f"  [Solar:{id_agente}] paso {paso_num} "
                      f"P={solar.P_real:.0f}W SoC={solar.SoC:.4f}")
    except KeyboardInterrupt:
        pass
    zmq.desconectar()
    print(f"[Solar:{id_agente}] Finalizado")


def main():
    parser = argparse.ArgumentParser(description="Co-simulacion 5 nodos, 1 hora")
    parser.add_argument("--local", action="store_true",
                        help="BESS + Solar en PC")
    parser.add_argument("--remoto", action="store_true",
                        help="BESS local, Solar via RPi")
    parser.add_argument("--solo-server", action="store_true",
                        help="Solo servidor (Solar desde RPi manual)")
    parser.add_argument("--plot-only", type=str, default=None,
                        help="Solo graficar desde CSV")
    args = parser.parse_args()

    if args.plot_only:
        _graficar(args.plot_only)
        return

    mode = "local" if args.local else ("remoto" if args.remoto else "solo-server")
    print(f"=== Co-simulacion distribuida: modo {mode} ===")
    print(f"Red: {ARCHIVO_RED}")
    print(f"Tiempo: {TIEMPO_TOTAL:.0f}s, paso: {PASO_MAESTRO}s "
          f"({int(TIEMPO_TOTAL / PASO_MAESTRO)} pasos)")
    print(f"Cargas: nodo2={CARGAS[2][0]:.0f}W, nodo4={CARGAS[4][0]:.0f}W")

    hilos = []

    try:
        r = RelojZMQ(puerto=PUERTO_ZMQ, paso_maestro=PASO_MAESTRO)
        r.iniciar()

        if mode == "local":
            t_bess = threading.Thread(
                target=_loop_bess_agent,
                args=(1, "127.0.0.1", PUERTO_ZMQ, 0.5, 100, 5000, 2.0, PASO_MAESTRO),
                daemon=True,
            )
            t_bess.start()
            hilos.append(t_bess)

            t_solar = threading.Thread(
                target=_loop_solar_agent,
                args=(2, "127.0.0.1", PUERTO_ZMQ, 3000, PASO_MAESTRO),
                daemon=True,
            )
            t_solar.start()
            hilos.append(t_solar)

            _time.sleep(0.5)

        elif mode == "remoto":
            t_bess = threading.Thread(
                target=_loop_bess_agent,
                args=(1, "127.0.0.1", PUERTO_ZMQ, 0.5, 100, 5000, 2.0, PASO_MAESTRO),
                daemon=True,
            )
            t_bess.start()
            hilos.append(t_bess)
            print("\n[Esperando agente Solar desde RPi...]")
            print("En RPi ejecutar:")
            print(f"  python ejecutar_agente_solar.py --id 2 "
                  f"--host 192.168.1.6 --puerto {PUERTO_ZMQ} "
                  f"--P_rated 3000 --modo local")
            print()

        else:
            print("\n[Modo solo servidor]")
            print("Conecta agentes externos via ZMQ en puerto", PUERTO_ZMQ)
            print("En RPi ejecutar:")
            print(f"  python ejecutar_agente_solar.py --id 2 "
                  f"--host 192.168.1.6 --puerto {PUERTO_ZMQ} "
                  f"--P_rated 3000 --modo local")
            print("En PC (otra terminal):")
            print(f"  python ejecutar_agente.py --id 1 --host 127.0.0.1 "
                  f"--puerto {PUERTO_ZMQ} --SoC 0.5 --P_rated 5000 "
                  f"--K_soc 2.0")
            print()

        n_con = r.esperar_agentes(N_AGENTES, timeout=120.0)
        print(f"[Server] {n_con}/{N_AGENTES} agentes conectados")

        mc = MasterClock(archivo_red=ARCHIVO_RED, paso_maestro=PASO_MAESTRO)
        SoCs = {1: 0.5, 2: 1.0}
        tiempo = 0.0
        paso = 0
        historial = []
        t_start = _time.time()

        while tiempo < TIEMPO_TOTAL:
            total_carga = abs(sum(p for p, _ in CARGAS.values()))
            SoC_avg = sum(SoCs.values()) / len(SoCs) if SoCs else 0.5
            extras = {
                "SoC_avg": round(SoC_avg, 6),
                "SoCs": {str(k): round(v, 6) for k, v in SoCs.items()},
                "num_agentes": N_AGENTES,
            }
            r.enviar_tick(paso, tiempo, {}, total_carga, extras)
            ms = r.recibir_mediciones(N_AGENTES)

            inyecciones = dict(CARGAS)
            potencias = {}
            for k, v in ms.items():
                nodo = AGENTE_NODO.get(k)
                if nodo is not None:
                    P_ag = v.get("P_ref", 0.0)
                    inyecciones[nodo] = (P_ag, 0.0)
                    potencias[k] = P_ag
                SoCs[k] = v.get("SoC", SoCs.get(k, 0.5))

            for n, (P, Q) in inyecciones.items():
                mc.registrar_inyeccion(n, P, Q)

            mc.step()

            historial.append({
                "tiempo": round(tiempo, 3),
                "V": {n: abs(mc.V[n]) if mc.V else 0.0
                      for n in range(mc.sweep.n_nodos)},
                "P_bess": potencias.get(1, 0.0),
                "P_solar": potencias.get(2, 0.0),
                "P_carga1": CARGAS[2][0],
                "P_carga2": CARGAS[4][0],
                "SoC_bess": SoCs.get(1, 0.0),
                "SoC_solar": SoCs.get(2, 0.0),
                "paso": paso,
            })

            tiempo = mc.tiempo
            paso += 1

            if paso % 2000 == 0:
                elapsed = _time.time() - t_start
                rate = paso / elapsed if elapsed > 0 else 0
                print(f"  paso {paso} t={tiempo:.0f}/{TIEMPO_TOTAL:.0f}s "
                      f"({rate:.0f} pasos/s) "
                      f"Pb={potencias.get(1, 0):.0f} "
                      f"Ps={potencias.get(2, 0):.0f} "
                      f"SoC={SoCs.get(1, 0):.3f}")

        t_elapsed = _time.time() - t_start
        r.detener()
        print(f"\nSimulacion completada: {paso} pasos "
              f"en {t_elapsed:.1f}s reales ({paso / t_elapsed:.0f} pasos/s)")

        csv_path = os.path.join(os.path.dirname(__file__), "sim_1hora_resultados.csv")
        _guardar_csv(csv_path, historial)
        print(f"Resultados: {csv_path}")
        _graficar(csv_path)

    finally:
        _time.sleep(0.5)


def _guardar_csv(path, historial):
    if not historial:
        return
    keys = list(historial[0].keys())
    v_keys = sorted([k for k in historial[0].get("V", {}).keys()])
    fieldnames = [k for k in keys if k != "V"] + [f"V{n}" for n in v_keys]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for h in historial:
            row = {k: h[k] for k in keys if k != "V"}
            for n, v in h.get("V", {}).items():
                row[f"V{n}"] = v
            w.writerow(row)


def _graficar(csv_path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("matplotlib no disponible")
        return

    import csv
    data = []
    with open(csv_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            data.append(row)

    if not data:
        print("CSV vacio")
        return

    t = [float(r["tiempo"]) for r in data]
    P_bess = [float(r["P_bess"]) for r in data]
    P_solar = [float(r["P_solar"]) for r in data]
    P_c1 = [float(r["P_carga1"]) for r in data]
    P_c2 = [float(r["P_carga2"]) for r in data]
    SoC_bess = [float(r["SoC_bess"]) for r in data]
    SoC_solar = [float(r["SoC_solar"]) for r in data]
    v_cols = sorted([c for c in data[0].keys() if c.startswith("V")],
                    key=lambda x: int(x[1:]))
    V = {c: [float(r[c]) for r in data] for c in v_cols}

    step_plot = max(1, len(t) // 5000)
    t_p = t[::step_plot]
    P_bess_p = P_bess[::step_plot]
    P_solar_p = P_solar[::step_plot]
    P_c1_p = P_c1[::step_plot]
    P_c2_p = P_c2[::step_plot]
    SoC_bess_p = SoC_bess[::step_plot]
    SoC_solar_p = SoC_solar[::step_plot]
    V_p = {c: V[c][::step_plot] for c in v_cols}

    fig, axes = plt.subplots(4, 1, figsize=(14, 14), sharex=True)

    ax = axes[0]
    for c in v_cols:
        ax.plot(t_p, V_p[c], label=f"Nodo {c}", linewidth=0.8)
    ax.axhline(0.95, color="gray", linestyle="--", alpha=0.5, label="0.95 pu")
    ax.axhline(1.05, color="gray", linestyle="--", alpha=0.5, label="1.05 pu")
    ax.set_ylabel("Tension [pu]")
    ax.set_title(f"Tensiones nodales (V_base=110V, {len(t)} pasos)")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    ax.plot(t_p, P_bess_p, label="BESS (nodo 1)", linewidth=0.8)
    ax.plot(t_p, P_solar_p, label="Solar (nodo 3)", linewidth=0.8)
    ax.plot(t_p, P_c1_p, label="Carga 1 (nodo 2)", linewidth=0.8, alpha=0.6)
    ax.plot(t_p, P_c2_p, label="Carga 2 (nodo 4)", linewidth=0.8, alpha=0.6)
    P_net = [a + b + c + d for a, b, c, d in
             zip(P_bess_p, P_solar_p, P_c1_p, P_c2_p)]
    ax.plot(t_p, P_net, label="Balance neto", linewidth=0.8,
            linestyle="--", color="black")
    ax.set_ylabel("Potencia [W]")
    ax.set_title("Potencia activa por nodo")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[2]
    ax.plot(t_p, SoC_bess_p, label="SoC BESS", linewidth=0.8)
    ax.plot(t_p, SoC_solar_p, label="Solar P/P_rated", linewidth=0.8)
    ax.set_ylabel("SoC / Cap. factor")
    ax.set_title("Estado de carga y factor de capacidad solar")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[3]
    V_arr = np.array([V[c] for c in v_cols])
    v_mean = np.mean(V_arr, axis=0)[::step_plot]
    v_min = np.min(V_arr, axis=0)[::step_plot]
    v_max = np.max(V_arr, axis=0)[::step_plot]
    ax.fill_between(t_p, v_min, v_max, alpha=0.2, color="blue",
                     label="Rango min-max")
    ax.plot(t_p, v_mean, label="Promedio", color="blue", linewidth=1.0)
    ax.axhline(1.0, color="black", linestyle="--", alpha=0.3)
    ax.set_xlabel("Tiempo [s]")
    ax.set_ylabel("Tension [pu]")
    ax.set_title("Estadisticas de tension nodal")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    png_path = csv_path.replace(".csv", ".png")
    plt.savefig(png_path, dpi=150)
    print(f"Grafica: {png_path}")

    print("Graficas generadas correctamente")


if __name__ == "__main__":
    main()
