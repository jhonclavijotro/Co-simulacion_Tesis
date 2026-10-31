import os
import sys
import math
import cmath
import csv
import json
import time
import glob
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Central_PC.power_flow_fbs import ForwardBackwardSweepSolver
from Agents.node_dynamic_process import NodeDynamicProcess
from Agents.finite_time_consensus import FixedTimeConsensusAgent
from mock_data.data_loader import MockDataLoader


class BTSimulationRunner:
    """
    Ejecutor de Co-Simulación para Microrred Radial en Baja Tensión (BT - 400V).

    La cantidad de nodos se descubre desde la topología cargada (6 u 8 nodos).
    Arquitectura de referencia (8 nodos):
      - Nodo 1: Diésel (Slack en Isla).
      - Nodo 2: Solar PV (datos_radiacion_temperatura.csv).
      - Nodo 3: BESS.
      - Nodos 4..8: 5 cargas (datos_demanda_A..E.csv).

    Prioridad de datos: escenario activo > ensayos_red_hil > formatos.
    Si el escenario activo incluye una topología, se usa esa; en caso
    contrario se mantiene config/topologia_BT_6nodos.csv (retrocompatible).
    """

    def __init__(
        self,
        topology_path: str = None,
        output_csv: str = "output_data/telemetry_monitor_formatos_bt.csv",
        v_base: float = None,
        s_base: float = None,
        dt: float = None
    ):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.base_dir = base_dir
        self.output_csv = os.path.abspath(os.path.join(base_dir, output_csv))
        os.makedirs(os.path.dirname(self.output_csv), exist_ok=True)

        # Resolver directorio de datos (escenario activo con prioridad)
        base_forms = os.path.join(base_dir, "Forms")
        ensayos_dir = os.path.join(base_forms, "ensayos_red_hil")
        legacy_dir = os.path.join(base_forms, "formatos")
        generados_dir = os.path.join(base_forms, "escenarios_generados")

        escenario_activo = self._resolver_escenario_activo(generados_dir)
        if escenario_activo:
            formatos_dir = escenario_activo
        else:
            formatos_dir = ensayos_dir if os.path.exists(ensayos_dir) else legacy_dir

        # 0. Capa 1: fuente de verdad de S_base, dt, tipos de nodo y límites DER.
        #    Prioridad: escenario activo > plantilla global de Forms.
        self.capa1_path, self.capa1, self.capa1_origen = self._cargar_capa1(
            escenario_activo, base_forms)

        pg = (self.capa1 or {}).get("parametros_generales", {})
        self.v_base = float(v_base) if v_base is not None else float(pg.get("tension_base_V", 400.0))
        self.s_base = (float(s_base) if s_base is not None
                       else float(pg.get("potencia_base_kVA", 10.0)) * 1000.0)
        self.dt = float(dt) if dt is not None else float(pg.get("paso_macro_reloj_s", 0.5))

        if self.capa1 is None:
            print("[WARN] Capa 1 no encontrada: se usan los valores por defecto "
                  "(retrocompatible con el banco de 6 nodos).")

        # Duración declarada por el escenario activo (para --steps por defecto).
        self.pasos_capa1 = None
        if self.capa1_origen == "escenario":
            duracion = pg.get("duracion_total_segundos")
            if duracion:
                self.pasos_capa1 = max(1, int(round(float(duracion) / self.dt)))

        # Topología: explícita > escenario activo > Capa 1 del escenario > 6 nodos por defecto
        if topology_path:
            self.topology_path = topology_path
        else:
            topo_escenario = None
            if escenario_activo:
                candidatas = sorted(glob.glob(os.path.join(escenario_activo, "topologia_*.csv")))
                if candidatas:
                    topo_escenario = candidatas[0]
            # La Capa 1 global no impone topología sin escenario activo
            # (se conserva el banco de 6 nodos como comportamiento heredado).
            if not topo_escenario and self.capa1_origen == "escenario":
                declarada = (self.capa1 or {}).get("archivos_topologia", {}).get("topologia_csv")
                if declarada:
                    candidata = self._resolver_ruta(formatos_dir, declarada)
                    if os.path.exists(candidata):
                        topo_escenario = candidata
            self.topology_path = topo_escenario or os.path.join(base_dir, "config", "topologia_BT_6nodos.csv")

        # 1. Solucionador de Red Radial FBS en Baja Tensión
        self.solver = ForwardBackwardSweepSolver(V_base=self.v_base, S_base=self.s_base)
        self.solver.load_topology(self.topology_path)
        self.nodos = list(self.solver.nodes)
        self.solver.set_operating_mode("OFFLINE", slack_node=1, V_slack=1.0)

        # 2. Procesos Dinámicos DERs (tipo declarado en Capa 1)
        asignacion = (self.capa1 or {}).get("asignacion_nodos", {})
        self.tipos_fuente = {
            n: asignacion.get(f"nodo_{n}", {}).get("tipo_fuente", defecto)
            for n, defecto in ((1, "DIESEL"), (2, "SOLAR"), (3, "BESS"))
        }
        self.proc_diesel = NodeDynamicProcess(node_id=1, source_type=self.tipos_fuente[1])
        self.proc_solar  = NodeDynamicProcess(node_id=2, source_type=self.tipos_fuente[2])
        self.proc_bess   = NodeDynamicProcess(node_id=3, source_type=self.tipos_fuente[3])

        # 3. Agentes de Consenso FxTS para Reparto de Reactiva (Q-sharing)
        # Capacidades efectivas: por defecto Diésel=10 kW/6 kvar, Solar=5/3, BESS=3/2.
        # La Capa 1 declara además p_nominal/q_nominal (placa) en 'capacidades_der'.
        caps = (self.capa1 or {}).get("capacidades_der", {})
        self.p_max = {
            n: float(caps.get(str(n), {}).get("p_max_W", defecto))
            for n, defecto in ((1, 10000.0), (2, 5000.0), (3, 3000.0))
        }
        self.q_max = {
            n: float(caps.get(str(n), {}).get("q_max_var", defecto))
            for n, defecto in ((1, 6000.0), (2, 3000.0), (3, 2000.0))
        }

        self.agent_1 = FixedTimeConsensusAgent(agent_id=1, Q_max=self.q_max[1], P_max=self.p_max[1], mode="OFFLINE", c1=0.25, c2=0.15)
        self.agent_2 = FixedTimeConsensusAgent(agent_id=2, Q_max=self.q_max[2], P_max=self.p_max[2], mode="OFFLINE", c1=0.25, c2=0.15)
        self.agent_3 = FixedTimeConsensusAgent(agent_id=3, Q_max=self.q_max[3], P_max=self.p_max[3], mode="OFFLINE", c1=0.25, c2=0.15)

        # Topología de comunicación: 1 <-> 2 <-> 3 (Capa 1 'grafo_consenso')
        self.agent_1.set_adjacency({2: 1.0})
        self.agent_2.set_adjacency({1: 1.0, 3: 1.0})
        self.agent_3.set_adjacency({2: 1.0})

        # 4. Cargar perfiles de demanda sintéticos (mapa nodo -> archivo de Capa 1)
        mapa_demanda = asignacion.get("nodos_demanda", {}).get("archivos_demanda") or {
            "4": "datos_demanda_A.csv",
            "5": "datos_demanda_B.csv",
            "6": "datos_demanda_C.csv",
            "7": "datos_demanda_D.csv",
            "8": "datos_demanda_E.csv",
        }
        self.demandas = {}
        for nodo, nombre in sorted(((int(k), v) for k, v in mapa_demanda.items()), key=lambda x: x[0]):
            ruta = self._resolver_ruta(formatos_dir, nombre)
            if nodo not in self.nodos:
                # Serie declarada para un nodo que esta topologia no tiene (p. ej. N7/N8
                # en el banco heredado de 6 nodos): se omite, no se exige el archivo.
                if not os.path.exists(ruta):
                    print(f"[WARN] N{nodo} no esta en {os.path.basename(self.topology_path)}: "
                          f"se omite su serie {nombre}.")
                continue
            self.demandas[nodo] = self._load_demanda_csv(ruta)

        # Atributos heredados (compatibilidad con scripts externos)
        self.demanda_A = self.demandas.get(4, [])
        self.demanda_B = self.demandas.get(5, [])
        self.demanda_C = self.demandas.get(6, [])
        self.demanda_D = self.demandas.get(7, [])
        self.demanda_E = self.demandas.get(8, [])

        self.nodos_carga = [n for n in sorted(self.demandas) if n in self.nodos]

        # Referencias de control iniciales (ratios desiguales para convergencia de consenso)
        self.Q_refs = {1: 1500.0, 2: 600.0, 3: 1000.0}
        self.P_refs = {1: 3000.0, 2: 2000.0, 3: 1000.0}
        self.f_sys = 60.0
        self.prev_theta_rad = {n: 0.0 for n in self.nodos}

    # ------------------------------------------------------------------
    # Capa 1
    # ------------------------------------------------------------------
    CAPA1_NOMBRE = "plantilla_configuracion_cosimulacion.json"

    def _cargar_capa1(self, escenario_activo, base_forms):
        """Carga y valida la Capa 1. Devuelve (ruta, datos, origen) o (None, None, None)."""
        candidatos = []
        if escenario_activo:
            candidatos.append((os.path.join(escenario_activo, self.CAPA1_NOMBRE), "escenario"))
        candidatos.append((os.path.join(base_forms, self.CAPA1_NOMBRE), "global"))

        for ruta, origen in candidatos:
            if not os.path.exists(ruta):
                continue
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError) as exc:
                raise ValueError(f"Capa 1 ilegible ({ruta}): {exc}")
            self._validar_capa1(data, ruta)
            return ruta, data, origen
        return None, None, None

    def _validar_capa1(self, data, ruta):
        """Falla si la Capa 1 no declara los parámetros que el runner consume."""
        faltan = []
        pg = data.get("parametros_generales")
        if not isinstance(pg, dict):
            raise ValueError(f"Capa 1 sin 'parametros_generales' ({ruta})")
        for clave in ("tension_base_V", "potencia_base_kVA", "paso_macro_reloj_s",
                      "tipo_malla", "modo_solucionador_potencia"):
            if clave not in pg:
                faltan.append(f"parametros_generales.{clave}")

        asignacion = data.get("asignacion_nodos", {})
        for n in (1, 2, 3):
            if "tipo_fuente" not in asignacion.get(f"nodo_{n}", {}):
                faltan.append(f"asignacion_nodos.nodo_{n}.tipo_fuente")

        caps = data.get("capacidades_der", {})
        for n in ("1", "2", "3"):
            for clave in ("p_max_W", "q_max_var"):
                if clave not in caps.get(n, {}):
                    faltan.append(f"capacidades_der.{n}.{clave}")

        if faltan:
            raise ValueError(
                f"Capa 1 incompleta ({ruta}). Faltan: " + ", ".join(faltan))

        if str(pg["modo_solucionador_potencia"]).upper() != "FBS":
            raise ValueError(
                f"El runner local solo implementa FBS; la Capa 1 declara "
                f"'{pg['modo_solucionador_potencia']}' ({ruta}).")
        if str(pg["tipo_malla"]).upper() != "RADIAL":
            raise ValueError(
                f"El runner local solo implementa red RADIAL; la Capa 1 declara "
                f"'{pg['tipo_malla']}' ({ruta}).")

    def _resolver_ruta(self, formatos_dir, nombre):
        """Resuelve un archivo declarado en Capa 1 (nombre suelto o ruta relativa)."""
        if not nombre:
            return formatos_dir
        if os.path.isabs(nombre):
            return nombre
        for candidato in (os.path.join(formatos_dir, nombre),
                          os.path.join(self.base_dir, nombre)):
            if os.path.exists(candidato):
                return candidato
        return os.path.join(formatos_dir, nombre)

    def _resolver_escenario_activo(self, generados_dir):
        """Devuelve la ruta del escenario activo si existe, o None."""
        marcador = os.path.join(generados_dir, "ACTIVO.txt")
        if not os.path.exists(marcador):
            return None
        try:
            with open(marcador, "r", encoding="utf-8") as f:
                nombre = f.read().strip()
        except OSError:
            return None
        if not nombre:
            return None
        ruta = os.path.join(generados_dir, nombre)
        return ruta if os.path.isdir(ruta) else None

    def _load_demanda_csv(self, file_path):
        """Carga una serie de demanda declarada en Capa 1. Falla si no existe o está vacía."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(
                f"Serie de demanda declarada en Capa 1 no encontrada: {file_path}. "
                "Corregir 'asignacion_nodos.nodos_demanda.archivos_demanda' o instalar el "
                "escenario completo antes de simular.")
        data = []
        with open(file_path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
        if not lines:
            raise ValueError(f"Serie de demanda vacía: {file_path}")
        delim = ";" if ";" in lines[0] else ","
        reader = csv.reader(lines, delimiter=delim)
        header = [h.strip() for h in next(reader, [])]
        p_idx = header.index("P_kW") if "P_kW" in header else (header.index("P") if "P" in header else 1)
        q_idx = header.index("Q_kvar") if "Q_kvar" in header else (header.index("Q") if "Q" in header else 2)

        for row in reader:
            if len(row) > max(p_idx, q_idx):
                try:
                    # P y Q en kW y kvar en el CSV -> convertir a W y var
                    p_w = float(row[p_idx].replace(",", ".")) * 1000.0
                    q_var = float(row[q_idx].replace(",", ".")) * 1000.0
                    data.append((p_w, q_var))
                except ValueError:
                    continue
        if not data:
            raise ValueError(
                f"Serie de demanda sin filas P/Q válidas: {file_path} "
                f"(columnas detectadas: {header})")
        return data

    def run(self, max_steps: int = 240):
        print("=" * 70)
        print(f" SIMULACIÓN COMPLETA MICRORRED BT (400V) - {max_steps * self.dt / 60:.1f} MINUTOS")
        print(f" - Capa 1:               "
              + (f"{os.path.basename(self.capa1_path)} ({self.capa1_origen})"
                 if self.capa1_path else "no disponible (valores por defecto)"))
        print(f" - Topología:            {os.path.basename(self.topology_path)}")
        print(f" - Tipo de malla:        {(self.capa1 or {}).get('parametros_generales', {}).get('tipo_malla', 'RADIAL')}")
        print(f" - Tensión Base:         {self.v_base} V (Baja Tensión)")
        print(f" - Potencia Base:        {self.s_base / 1000.0:.1f} kVA")
        print(f" - Tipos DER:            " + ", ".join(
            f"N{n}={self.tipos_fuente[n]}" for n in (1, 2, 3)))
        print(f" - Límites agentes:      " + ", ".join(
            f"N{n}={self.p_max[n] / 1000.0:.1f}kW/{self.q_max[n] / 1000.0:.1f}kvar" for n in (1, 2, 3)))
        print(f" - Duración:             {max_steps} pasos ({max_steps * self.dt:.1f} s / {max_steps * self.dt / 60:.1f} min)")
        print(f" - Nodos en topología:   {len(self.nodos)} {self.nodos}")
        print(f" - Nodos de carga:       {self.nodos_carga}")
        print(f" - Muestras Demandas:    " + ", ".join(
            f"N{n}={len(self.demandas[n])}" for n in self.nodos_carga))
        print(f" - Archivo de Salida:    {self.output_csv}")
        print("=" * 70)

        # Inicializar CSV con cabeceras estándar de tesis (una columna por nodo)
        headers = ["step", "time_sec", "f_sys_hz", "P_net_kW"]
        headers += [f"V{n}_pu" for n in self.nodos]
        headers += [f"V{n}_V" for n in self.nodos]
        headers += [f"f{n}_hz" for n in self.nodos]
        headers += [f"theta{n}_deg" for n in self.nodos]
        headers += [
            "Q_ratio_1", "Q_ratio_2", "Q_ratio_3",
            "error_Q_12", "error_Q_23", "error_V_12", "error_V_23"
        ]
        with open(self.output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

        # Respaldo por nodo si falta la serie (mantiene la operación del lazo)
        fallback = {4: (2850.0, 936.0), 5: (1960.0, 398.0), 6: (1470.0, 298.0),
                    7: (2500.0, 1000.0), 8: (2000.0, 800.0)}

        voltages_dict = {n: 1.0 for n in self.nodos}
        start_wall = time.perf_counter()

        for step in range(1, max_steps + 1):
            t_sec = step * self.dt
            idx = step - 1

            # 1. Obtener demanda de cada nodo de carga desde las series temporales
            demandas_paso = {}
            for n in self.nodos_carga:
                serie = self.demandas[n]
                demandas_paso[n] = serie[idx % len(serie)] if serie else fallback.get(n, (0.0, 0.0))

            # 2. Paso de dinámica física para cada DER con la tensión de su nodo
            V1_volts = voltages_dict[1] * self.v_base
            V2_volts = voltages_dict[2] * self.v_base
            V3_volts = voltages_dict[3] * self.v_base

            out_diesel = self.proc_diesel.step_macro(V_pcc=V1_volts, Q_ref=self.Q_refs[1], P_ref=self.P_refs[1], macro_dt=self.dt)
            out_solar  = self.proc_solar.step_macro(V_pcc=V2_volts, Q_ref=self.Q_refs[2], P_ref=self.P_refs[2], macro_dt=self.dt)
            out_bess   = self.proc_bess.step_macro(V_pcc=V3_volts, Q_ref=self.Q_refs[3], P_ref=self.P_refs[3], macro_dt=self.dt)

            P1, Q1 = out_diesel["P_w"], out_diesel["Q_var"]
            P2, Q2 = out_solar["P_w"],  out_solar["Q_var"]
            P3, Q3 = out_bess["P_w"],   out_bess["Q_var"]

            # Ratios de potencia reactiva
            q_ratio_1 = Q1 / self.q_max[1]
            q_ratio_2 = Q2 / self.q_max[2]
            q_ratio_3 = Q3 / self.q_max[3]

            # 3. Consenso FxTS P2P para reparto de reactiva
            states = {
                1: {"V": voltages_dict[1], "Q_ratio": q_ratio_1, "omega": 2 * math.pi * self.f_sys},
                2: {"V": voltages_dict[2], "Q_ratio": q_ratio_2, "omega": 2 * math.pi * self.f_sys},
                3: {"V": voltages_dict[3], "Q_ratio": q_ratio_3, "omega": 2 * math.pi * self.f_sys}
            }

            _, dQ1, _, _ = self.agent_1.update_consensus(voltages_dict[1], Q1, {2: states[2]}, dt=self.dt, return_all=True)
            _, dQ2, _, _ = self.agent_2.update_consensus(voltages_dict[2], Q2, {1: states[1], 3: states[3]}, dt=self.dt, return_all=True)
            _, dQ3, _, _ = self.agent_3.update_consensus(voltages_dict[3], Q3, {2: states[2]}, dt=self.dt, return_all=True)

            self.Q_refs[1] = max(0.0, min(self.q_max[1], self.Q_refs[1] + dQ1))
            self.Q_refs[2] = max(0.0, min(self.q_max[2], self.Q_refs[2] + dQ2))
            self.Q_refs[3] = max(0.0, min(self.q_max[3], self.Q_refs[3] + dQ3))

            # 4. Inyecciones netas para el flujo de potencia FBS (Cargas consumen: signo negativo)
            P_inj = {1: P1, 2: P2, 3: P3}
            Q_inj = {1: Q1, 2: Q2, 3: Q3}
            for n, (P_dem, Q_dem) in demandas_paso.items():
                P_inj[n] = -P_dem
                Q_inj[n] = -Q_dem

            # 5. Resolver flujo de potencia Forward-Backward Sweep
            voltages_complex, conv, iters = self.solver.solve(P_inj, Q_inj)
            thetas_deg = {}
            f_nodes = {}
            for n in self.nodos:
                v_c = voltages_complex.get(n, 1.0 + 0.0j)
                voltages_dict[n] = abs(v_c)
                th_rad = cmath.phase(v_c)
                thetas_deg[n] = math.degrees(th_rad)

                if n in (1, 2, 3):
                    # Frecuencia estimada por el lazo SRF-PLL / gobernador del inversor/generador
                    gen_out = {1: out_diesel, 2: out_solar, 3: out_bess}[n]
                    f_nodes[n] = float(gen_out.get("Fsys", self.f_sys))
                else:
                    # Frecuencia local en barra de carga derivada de la variación angular d_theta/dt
                    d_th = th_rad - self.prev_theta_rad.get(n, th_rad)
                    d_th = (d_th + math.pi) % (2.0 * math.pi) - math.pi
                    f_nodes[n] = self.f_sys + d_th / (2.0 * math.pi * self.dt)

                self.prev_theta_rad[n] = th_rad

            # 6. Dinámica de frecuencia del sistema
            self.f_sys, p_net_w = self.solver.compute_frequency_dynamics(P_inj, f_prev=self.f_sys, dt=self.dt, f_nom=60.0)

            # Métricas de error y convergencia
            err_q_12 = abs(q_ratio_1 - q_ratio_2)
            err_q_23 = abs(q_ratio_2 - q_ratio_3)
            err_v_12 = abs(voltages_dict[1] - voltages_dict[2])
            err_v_23 = abs(voltages_dict[2] - voltages_dict[3])

            v_pu = [voltages_dict[i] for i in self.nodos]
            v_volts = [voltages_dict[i] * self.v_base for i in self.nodos]
            p_net_kw = p_net_w / 1000.0

            # 7. Registrar fila en CSV
            row = [step, round(t_sec, 2), round(self.f_sys, 4), round(p_net_kw, 2)]
            row += [round(x, 5) for x in v_pu]
            row += [round(x, 2) for x in v_volts]
            row += [round(f_nodes[i], 4) for i in self.nodos]
            row += [round(thetas_deg[i], 3) for i in self.nodos]
            row += [
                round(q_ratio_1, 4), round(q_ratio_2, 4), round(q_ratio_3, 4),
                round(err_q_12, 4), round(err_q_23, 4),
                round(err_v_12, 5), round(err_v_23, 5)
            ]
            with open(self.output_csv, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(row)

            # Registro en consola cada 20 pasos (cada 10 segundos)
            if step % 20 == 0 or step == 1:
                p_dem_total = sum(v[0] for v in demandas_paso.values()) / 1000.0
                p_gen_total = (P1 + P2 + P3) / 1000.0
                f_min_n = min(f_nodes.values())
                f_max_n = max(f_nodes.values())
                print(f"[{step:03d}/{max_steps}] t={t_sec:5.1f}s | f_sys={self.f_sys:.3f}Hz (f_min={f_min_n:.3f}, f_max={f_max_n:.3f}) | "
                      f"Gen={p_gen_total:.2f}kW, Dem={p_dem_total:.2f}kW | "
                      f"Q_ratios=({q_ratio_1:.3f}, {q_ratio_2:.3f}, {q_ratio_3:.3f}) | Err_Q12={err_q_12:.4f} | Vmin={min(v_pu):.4f}pu")

        elapsed = time.perf_counter() - start_wall
        print("=" * 70)
        print(f" SIMULACIÓN DE {max_steps * self.dt / 60:.1f} MINUTOS COMPLETADA EN {elapsed:.2f} s")
        print(f" Archivo generado: {self.output_csv}")
        print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulación Microrred BT con datos de Formatos")
    parser.add_argument("--steps", type=int, default=None,
                        help="Número de pasos. Por defecto: la duración de la Capa 1 si hay "
                             "escenario activo (p. ej. 600 = 300 s @ 500 ms), o 240 si no.")
    parser.add_argument("--output-csv", default="output_data/telemetry_monitor_formatos_bt.csv", help="Ruta archivo CSV")
    args = parser.parse_args()

    runner = BTSimulationRunner(output_csv=args.output_csv)
    steps = args.steps if args.steps is not None else (runner.pasos_capa1 or 240)
    runner.run(max_steps=steps)
