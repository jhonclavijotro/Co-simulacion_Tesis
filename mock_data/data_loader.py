import csv
import os

class MockDataLoader:
    """
    Cargador ligero de datos meteorológicos sintéticos usando la librería estándar csv de Python.
    No requiere dependencias externas ni DLLs bloqueadas.
    Discretización: 500 ms (2 Hz).
    """
    def __init__(self, data_dir=None):
        if data_dir is None:
            data_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = data_dir
        
        self.solar_file = os.path.join(self.data_dir, "datos_meteorologicos_sinteticos.csv")
        self.eolic_file = os.path.join(self.data_dir, "datos_meteorologicos_eolicos_sinteticos.csv")
        self.hydro_file = os.path.join(self.data_dir, "datos_meteorologicos_hidricos_sinteticos.csv")
        
        self.solar_data = []
        self.eolic_data = []
        self.hydro_data = []
        
        self.load_all()

    def load_all(self):
        if os.path.exists(self.solar_file):
            with open(self.solar_file, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                self.solar_data = [{"POA": float(r["POA"]), "T_amb": float(r["T_amb"])} for r in reader]

        if os.path.exists(self.eolic_file):
            with open(self.eolic_file, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                self.eolic_data = [float(r["Ws"]) for r in reader]

        if os.path.exists(self.hydro_file):
            with open(self.hydro_file, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                self.hydro_data = [float(r["Vc"]) for r in reader]

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
    print(f"Cargador puramente nativo en Python. Muestras cargadas -> Solar: {len(loader.solar_data)}, Eólico: {len(loader.eolic_data)}, Hídrico: {len(loader.hydro_data)}")
    poa, temp = loader.get_solar_at(10)
    ws = loader.get_eolic_at(10)
    vc = loader.get_hydro_at(10)
    print(f"Muestra paso 10 -> Solar: POA={poa} W/m2, T={temp} K | Eólico: Ws={ws} m/s | Hídrico: Vc={vc} m/s")
