import csv
import json
import os
import re


ARCHIVO_METEO = "datos_meteorologicos.csv"
ARCHIVO_CAPA1 = "plantilla_configuracion_cosimulacion.json"

# Resolución de columna por entero de prefijo (`N1_` NO coincide con `N10_`).
RE_COL_METEO = re.compile(
    r"^N(\d+)_(POA_W_m2|T_amb_C|T_amb_K|vel_viento_m_s|vel_agua_m_s)$"
)

TIPOS_SOLAR = {"SOLAR"}
TIPOS_EOLICA = {"EOLICA", "EÓLICA"}
TIPOS_HIDRO = {"HIDRICA", "HÍDRICA", "HIDROCINETICA", "HIDROCINÉTICA"}


class MissingResourceDataError(RuntimeError):
    """Un recurso declarado en la Capa 1 no tiene columna/serie utilizable.

    Política de fallo fuerte (S-O-05, enmienda (b)): nunca se sustituye una
    temperatura por 298.15 K ni una velocidad por 0 m/s cuando el recurso está
    instanciado. Si el dato falta, la simulación se detiene con este error.
    """


class MockDataLoader:
    """
    Cargador de datos meteorológicos para la arquitectura de co-simulación.

    Dos modos, elegidos automáticamente:

    - **consolidado** (rev.5, D-03): si el escenario activo contiene
      `datos_meteorologicos.csv`, se lee ese archivo y sus columnas
      `N{id}_POA_W_m2`, `N{id}_T_amb_C`, `N{id}_T_amb_K`,
      `N{id}_vel_viento_m_s`, `N{id}_vel_agua_m_s`. No hay cascada a archivos
      legacy: si la Capa 1 declara un recurso y su columna falta, se lanza
      `MissingResourceDataError`.
    - **legacy**: escenarios anteriores a 2026-11-01 (un archivo por
      tecnología). Se conserva la cascada histórica para no romper el banco
      activo mientras se migra.

    La selección de columna se hace por nombre y número de nodo, nunca por
    posición ni por `startswith`.
    """

    def __init__(self, data_dir=None, escenario_dir=None):
        if data_dir is None:
            data_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = data_dir
        self.forms_dir = os.path.abspath(os.path.join(self.data_dir, "..", "Forms"))
        self.ensayos_dir = os.path.join(self.forms_dir, "ensayos_red_hil")
        self.sinteticas_dir = os.path.join(self.forms_dir, "pruebas_sinteticas")
        self.legacy_formatos_dir = os.path.join(self.forms_dir, "formatos")
        self.generados_dir = os.path.join(self.forms_dir, "escenarios_generados")
        self.escenario_activo_dir = self._resolver_escenario_activo()
        self.escenario_dir = escenario_dir or self.escenario_activo_dir

        self.modo = "legacy"
        self.columnas_meteo = {}
        self.solar_node = None
        self.eolic_node = None
        self.hydro_node = None

        self.solar_data = []
        self.eolic_data = []
        self.hydro_data = []

        ruta_meteo = (os.path.join(self.escenario_dir, ARCHIVO_METEO)
                      if self.escenario_dir else None)
        if ruta_meteo and os.path.exists(ruta_meteo):
            self.modo = "consolidado"
            self.ruta_meteo = ruta_meteo

        self.load_all()

    # ------------------------------------------------------------------
    # Resolución del escenario
    # ------------------------------------------------------------------
    def _resolver_escenario_activo(self):
        """Devuelve la ruta del escenario activo si existe, o None."""
        marcador = os.path.join(self.generados_dir, "ACTIVO.txt")
        if not os.path.exists(marcador):
            return None
        try:
            with open(marcador, "r", encoding="utf-8") as f:
                # `utf-8-sig`-like hardening: si el marcador se escribió con BOM
                # (p. ej. `Set-Content -Encoding utf8` en PowerShell 5.1), el
                # nombre no debe quedar invisible y caer al banco legacy.
                nombre = f.read().lstrip("\ufeff").strip()
        except OSError:
            return None
        if not nombre:
            return None
        ruta = os.path.join(self.generados_dir, nombre)
        return ruta if os.path.isdir(ruta) else None

    # ------------------------------------------------------------------
    # Utilidades de lectura
    # ------------------------------------------------------------------
    def _detect_delimiter_and_read(self, file_path):
        """Lee un CSV detectando delimitador (, o ;) y normalizando comas decimales."""
        if not os.path.exists(file_path):
            return []

        rows = []
        with open(file_path, mode="r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
            if not lines:
                return []

            delim = ";" if ";" in lines[0] else ","
            reader = csv.reader(lines, delimiter=delim)
            header = [h.strip() for h in next(reader, [])]

            for row in reader:
                if not row:
                    continue
                cleaned_row = [c.strip().replace(",", ".") for c in row]
                row_dict = {}
                for idx, col_name in enumerate(header):
                    if idx < len(cleaned_row):
                        row_dict[col_name] = cleaned_row[idx]
                rows.append(row_dict)
        return rows

    @staticmethod
    def _leer_crudo(file_path):
        """Devuelve (cabecera, filas) sin interpretar tipos."""
        with open(file_path, "r", encoding="utf-8", newline="") as f:
            lines = [l for l in f if l.strip() and not l.strip().startswith("#")]
        if not lines:
            raise MissingResourceDataError(f"Archivo de datos vacío: {file_path}")
        delim = ";" if ";" in lines[0] else ","
        reader = csv.reader(lines, delimiter=delim)
        header = [h.strip() for h in next(reader, [])]
        filas = [[c.strip().replace(",", ".") for c in row] for row in reader if row]
        return header, filas

    @staticmethod
    def _columna_numerica(filas, idx, columna, ruta):
        """Extrae una columna como float; NaN/vacíos son error (no se imputan)."""
        valores = []
        for n, fila in enumerate(filas, start=2):
            if idx >= len(fila):
                raise MissingResourceDataError(
                    f"{os.path.basename(ruta)}: fila {n} sin la columna '{columna}'.")
            crudo = fila[idx]
            try:
                valor = float(crudo)
            except (TypeError, ValueError):
                raise MissingResourceDataError(
                    f"{os.path.basename(ruta)}: valor no numérico en '{columna}' "
                    f"(fila {n}: '{crudo}').")
            if valor != valor:  # NaN
                raise MissingResourceDataError(
                    f"{os.path.basename(ruta)}: NaN en '{columna}' (fila {n}).")
            valores.append(valor)
        return valores

    # ------------------------------------------------------------------
    # Capa 1: recursos declarados
    # ------------------------------------------------------------------
    def _recursos_declarados_capa1(self):
        """{tipo_fuente_upper: nodo} según la Capa 1 del escenario, o None si no hay."""
        if not self.escenario_dir:
            return None
        ruta = os.path.join(self.escenario_dir, ARCHIVO_CAPA1)
        if not os.path.exists(ruta):
            return None
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return None

        declarados = {}
        for clave, entrada in (data.get("asignacion_nodos") or {}).items():
            match = re.match(r"^nodo_(\d+)$", str(clave))
            if not match:
                continue
            tipo = str((entrada or {}).get("tipo_fuente", "")).strip().upper()
            if tipo:
                declarados.setdefault(tipo, int(match.group(1)))
        return declarados

    # ------------------------------------------------------------------
    # Carga
    # ------------------------------------------------------------------
    def load_all(self):
        if self.modo == "consolidado":
            self._load_consolidado()
        else:
            self._load_legacy()

    def _load_consolidado(self):
        header, filas = self._leer_crudo(self.ruta_meteo)
        if header[:2] != ["timestamp", "tiempo_s"]:
            raise MissingResourceDataError(
                f"{os.path.basename(self.ruta_meteo)}: se esperaba la cabecera "
                f"'timestamp,tiempo_s,...' (D-03 rev.5); encontrada: {header[:2]}.")

        columnas = {}
        for idx, columna in enumerate(header):
            match = RE_COL_METEO.match(columna)
            if match:
                nodo = int(match.group(1))
                sufijo = match.group(2)
                columnas[(nodo, sufijo)] = self._columna_numerica(
                    filas, idx, columna, self.ruta_meteo)
        self.columnas_meteo = columnas

        declarados = self._recursos_declarados_capa1() or {}

        self.solar_node = self._resolver_recurso(
            columnas, ("POA_W_m2", "T_amb_C", "T_amb_K"),
            declarados, TIPOS_SOLAR, "solar")
        self.eolic_node = self._resolver_recurso(
            columnas, ("vel_viento_m_s",), declarados, TIPOS_EOLICA, "eólico")
        self.hydro_node = self._resolver_recurso(
            columnas, ("vel_agua_m_s",), declarados, TIPOS_HIDRO, "hidrocinético")

        if self.solar_node is not None:
            poa = columnas[(self.solar_node, "POA_W_m2")]
            t_k = columnas[(self.solar_node, "T_amb_K")]
            self.solar_data = [{"POA": p, "T_amb": t} for p, t in zip(poa, t_k)]

        if self.eolic_node is not None:
            self.eolic_data = list(columnas[(self.eolic_node, "vel_viento_m_s")])

        if self.hydro_node is not None:
            self.hydro_data = list(columnas[(self.hydro_node, "vel_agua_m_s")])

    def _resolver_recurso(self, columnas, sufijos, declarados, tipos, etiqueta):
        """Nodo del recurso, verificando que existan todas sus columnas."""
        nodo_declarado = next(
            (declarados[t] for t in tipos if t in declarados), None)
        nodos_presentes = sorted({
            nodo for (nodo, sufijo) in columnas if sufijo in sufijos
        })

        if nodo_declarado is not None:
            faltan = [s for s in sufijos if (nodo_declarado, s) not in columnas]
            if faltan:
                raise MissingResourceDataError(
                    f"La Capa 1 declara el recurso {etiqueta} en N{nodo_declarado}, "
                    f"pero {os.path.basename(self.ruta_meteo)} no tiene "
                    f"{', '.join(f'N{nodo_declarado}_{s}' for s in faltan)}. "
                    "No se imputa un valor por defecto (política de fallo fuerte).")
            return nodo_declarado

        if len(nodos_presentes) > 1:
            raise MissingResourceDataError(
                f"{os.path.basename(self.ruta_meteo)} declara el recurso {etiqueta} "
                f"en varios nodos {nodos_presentes} sin Capa 1 que lo desambigüe.")
        return nodos_presentes[0] if nodos_presentes else None

    def _load_legacy(self):
        """Cascada histórica (escenarios pre-2026-11-01). Sin cambios de semántica."""
        esc_activo = self.escenario_activo_dir

        # 1. Solar: escenario activo -> ensayo HIL -> sintético 24h -> formatos
        solar_files = []
        if esc_activo:
            solar_files.append(os.path.join(esc_activo, "datos_radiacion_temperatura.csv"))
        solar_files += [
            os.path.join(self.ensayos_dir, "datos_radiacion_temperatura.csv"),
            os.path.join(self.sinteticas_dir, "datos_solar_sintetico_24h.csv"),
            os.path.join(self.legacy_formatos_dir, "datos_radiacion_temperatura.csv"),
            os.path.join(self.data_dir, "datos_meteorologicos_sinteticos.csv")
        ]

        for s_file in solar_files:
            if os.path.exists(s_file):
                records = self._detect_delimiter_and_read(s_file)
                if records:
                    t_key = next((k for k in ("T_amb_K", "Tmp_K") if k in records[0]), None)
                    for r in records:
                        try:
                            poa = float(r.get("POA_W_m2") or r.get("POA", 0.0))
                            if t_key:
                                t_amb = float(r[t_key])
                            elif "T_amb_C" in r:
                                t_amb = float(r["T_amb_C"]) + 273.15
                            else:
                                t_amb = float(r.get("T_amb", 298.15))
                            self.solar_data.append({"POA": poa, "T_amb": t_amb})
                        except (ValueError, TypeError):
                            continue
                    if self.solar_data:
                        break

        # 2. Eólico
        eolic_files = []
        if esc_activo:
            eolic_files.append(os.path.join(esc_activo, "datos_vel_viento.csv"))
        eolic_files += [
            os.path.join(self.ensayos_dir, "datos_vel_viento.csv"),
            os.path.join(self.sinteticas_dir, "datos_eolica_sintetico_24h.csv"),
            os.path.join(self.legacy_formatos_dir, "datos_vel_viento.csv"),
            os.path.join(self.data_dir, "datos_meteorologicos_eolicos_sinteticos.csv")
        ]

        for w_file in eolic_files:
            if os.path.exists(w_file):
                records = self._detect_delimiter_and_read(w_file)
                if records:
                    for r in records:
                        try:
                            ws = float(r.get("vel_viento_m_s") or r.get("vel_viento") or r.get("Ws", 0.0))
                            self.eolic_data.append(ws)
                        except (ValueError, TypeError):
                            continue
                    if self.eolic_data:
                        break

        # 3. Hídrico
        hydro_files = []
        if esc_activo:
            hydro_files.append(os.path.join(esc_activo, "datos_hidrico_sintetico.csv"))
        hydro_files += [
            os.path.join(self.sinteticas_dir, "datos_hidrico_sintetico_24h.csv"),
            os.path.join(self.data_dir, "datos_meteorologicos_hidricos_sinteticos.csv")
        ]

        for h_file in hydro_files:
            if os.path.exists(h_file):
                records = self._detect_delimiter_and_read(h_file)
                if records:
                    for r in records:
                        try:
                            vc = float(r.get("vel_agua_m_s") or r.get("Vc", 0.0))
                            self.hydro_data.append(vc)
                        except (ValueError, TypeError):
                            continue
                    if self.hydro_data:
                        break

    # ------------------------------------------------------------------
    # Consulta por paso y por nodo
    # ------------------------------------------------------------------
    @staticmethod
    def _verificar_nodo(etiqueta, nodo_serie, node_id):
        if node_id is not None and nodo_serie is not None and int(node_id) != int(nodo_serie):
            raise ValueError(
                f"Se pidió el recurso {etiqueta} para N{node_id}, pero el escenario "
                f"lo declara en N{nodo_serie}.")

    def _valor_en(self, serie, step_idx, etiqueta):
        if not serie:
            if self.modo == "consolidado":
                raise MissingResourceDataError(
                    f"El recurso {etiqueta} no está instanciado en "
                    f"{os.path.basename(self.ruta_meteo)}.")
            return None
        if step_idx < len(serie):
            return serie[step_idx]
        if self.modo == "consolidado":
            raise MissingResourceDataError(
                f"El recurso {etiqueta} no tiene muestra para el paso {step_idx} "
                f"(serie de {len(serie)} muestras). Revisar duración/pasos: la serie "
                "solo cubre la duración declarada en la Capa 1.")
        return None

    def get_solar_at(self, step_idx, node_id=None):
        self._verificar_nodo("solar", self.solar_node, node_id)
        valor = self._valor_en(self.solar_data, step_idx, "solar")
        if valor is None:
            return 0.0, 298.15  # Solo en modo legacy (semántica histórica)
        return valor["POA"], valor["T_amb"]

    def get_eolic_at(self, step_idx, node_id=None):
        self._verificar_nodo("eólico", self.eolic_node, node_id)
        valor = self._valor_en(self.eolic_data, step_idx, "eólico")
        return 0.0 if valor is None else valor

    def get_hydro_at(self, step_idx, node_id=None):
        self._verificar_nodo("hidrocinético", self.hydro_node, node_id)
        valor = self._valor_en(self.hydro_data, step_idx, "hidrocinético")
        return 0.0 if valor is None else valor

    def total_steps(self):
        if self.modo == "consolidado":
            longitudes = [len(s) for s in (self.solar_data, self.eolic_data, self.hydro_data) if s]
            return max(longitudes) if longitudes else 0
        lengths = [len(self.solar_data), len(self.eolic_data), len(self.hydro_data)]
        valid = [l for l in lengths if l > 0]
        return min(valid) if valid else 0

    # Alias explícito para los consumidores que quieren distinguir el formato.
    @property
    def esquema(self):
        return self.modo


if __name__ == "__main__":
    loader = MockDataLoader()
    print(f"Esquema: {loader.esquema} | nodos solar={loader.solar_node} "
          f"eólico={loader.eolic_node} hidro={loader.hydro_node}")
    print(f"Muestras -> Solar: {len(loader.solar_data)}, "
          f"Eólico: {len(loader.eolic_data)}, Hídrico: {len(loader.hydro_data)}")
    poa, temp = loader.get_solar_at(10)
    ws = loader.get_eolic_at(10)
    vc = loader.get_hydro_at(10)
    print(f"Muestra paso 10 -> Solar: POA={poa} W/m2, T={temp} K | "
          f"Eólico: Ws={ws} m/s | Hídrico: Vc={vc} m/s")
