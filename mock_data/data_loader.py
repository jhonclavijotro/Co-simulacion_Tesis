import csv
import os

class MockDataLoader:
    """
    Cargador de datos meteorológicos unificado para la arquitectura de co-simulación.
    Soporta formato canónico internacional (coma ',', punto decimal '.') y compatibilidad
    hacia atrás con formatos heredados (';').
    
    Rutas prioritarias:
      0. Forms/escenarios_generados/<ESC_ACTIVO>/ (si existe ACTIVO.txt)
      1. Forms/ensayos_red_hil/ (datos experimentales / HIL de 2 minutos)
      2. Forms/pruebas_sinteticas/ (series sintéticas continuas de 24 horas a 2 Hz)
      3. Fallback en rutas locales / históricas.
      
    Discretización: 500 ms (2 Hz).
    """
    def __init__(self, data_dir=None):
        if data_dir is None:
            data_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = data_dir
        self.forms_dir = os.path.abspath(os.path.join(self.data_dir, "..", "Forms"))
        self.ensayos_dir = os.path.join(self.forms_dir, "ensayos_red_hil")
        self.sinteticas_dir = os.path.join(self.forms_dir, "pruebas_sinteticas")
        self.legacy_formatos_dir = os.path.join(self.forms_dir, "formatos")
        self.generados_dir = os.path.join(self.forms_dir, "escenarios_generados")
        self.escenario_activo_dir = self._resolver_escenario_activo()
        
        self.solar_data = []
        self.eolic_data = []
        self.hydro_data = []
        
        self.load_all()

    def _resolver_escenario_activo(self):
        """Devuelve la ruta del escenario activo si existe, o None."""
        marcador = os.path.join(self.generados_dir, "ACTIVO.txt")
        if not os.path.exists(marcador):
            return None
        try:
            with open(marcador, "r", encoding="utf-8") as f:
                nombre = f.read().strip()
        except OSError:
            return None
        if not nombre:
            return None
        ruta = os.path.join(self.generados_dir, nombre)
        return ruta if os.path.isdir(ruta) else None

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
                # Mapear columnas limpiando espacios y reemplazando comas decimales
                cleaned_row = [c.strip().replace(",", ".") for c in row]
                row_dict = {}
                for idx, col_name in enumerate(header):
                    if idx < len(cleaned_row):
                        row_dict[col_name] = cleaned_row[idx]
                rows.append(row_dict)
        return rows

    def load_all(self):
        # Prioridad 0: escenario activo (si existe)
        esc_activo = self.escenario_activo_dir

        # 1. Cargar Solar: Prioridad 0 Escenario Activo -> 1 Ensayo HIL -> 2 Sintético 24h
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
                    for r in records:
                        try:
                            # Claves estándar: POA_W_m2, POA. Temperatura: T_amb_K, Tmp_K, T_amb
                            poa = float(r.get("POA_W_m2") or r.get("POA", 0.0))
                            t_amb = float(r.get("T_amb_K") or r.get("Tmp_K") or r.get("T_amb", 298.15))
                            self.solar_data.append({"POA": poa, "T_amb": t_amb})
                        except (ValueError, TypeError):
                            continue
                    if self.solar_data:
                        break

        # 2. Cargar Eólico: Prioridad 0 Escenario Activo -> 1 Ensayo HIL -> 2 Sintético 24h
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

        # 3. Cargar Hídrico
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

    def get_solar_at(self, step_idx):
        if step_idx < len(self.solar_data):
            d = self.solar_data[step_idx]
            return d["POA"], d["T_amb"]
        return 0.0, 298.15  # Fallback: 0 W/m2, 25 °C (298.15 K)

    def get_eolic_at(self, step_idx):
        if step_idx < len(self.eolic_data):
            return self.eolic_data[step_idx]
        return 0.0  # Fallback: 0 m/s

    def get_hydro_at(self, step_idx):
        if step_idx < len(self.hydro_data):
            return self.hydro_data[step_idx]
        return 0.0  # Fallback: 0 m/s

    def total_steps(self):
        lengths = [len(self.solar_data), len(self.eolic_data), len(self.hydro_data)]
        valid = [l for l in lengths if l > 0]
        return min(valid) if valid else 0

if __name__ == "__main__":
    loader = MockDataLoader()
    print(f"Cargador unificado de datos. Muestras -> Solar: {len(loader.solar_data)}, Eólico: {len(loader.eolic_data)}, Hídrico: {len(loader.hydro_data)}")
    poa, temp = loader.get_solar_at(10)
    ws = loader.get_eolic_at(10)
    vc = loader.get_hydro_at(10)
    print(f"Muestra paso 10 -> Solar: POA={poa} W/m2, T={temp} K | Eólico: Ws={ws} m/s | Hídrico: Vc={vc} m/s")
