import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mock_data.data_loader import MockDataLoader
from Solar.SistemaSolar import SistemaSolar
from Eolica.SistemaEolico import SistemaEolico
from Hidrica.SistemaHidrico import SistemaHidrico
from BESS.SistemaBESS import SistemaBESS
from Diesel.SistemaDiesel import SistemaDiesel
from Demanda.SistemaDemanda import SistemaDemanda

class NodeDynamicProcess:
    """
    Proceso ejecutable de la Dinámica Físico-Eléctrica por Nodo.
    Lee series temporales desde mock_data y calcula la respuesta física del generador.
    """
    def __init__(self, node_id, source_type="SOLAR"):
        self.node_id = node_id
        self.source_type = source_type.upper()
        self.data_loader = MockDataLoader()
        self.step_index = 0

        # Inicialización del modelo dinámico
        if self.source_type == "SOLAR":
            self.model = SistemaSolar()
        elif self.source_type == "EOLICA":
            self.model = SistemaEolico()
        elif self.source_type == "HIDRICA":
            self.model = SistemaHidrico()
        elif self.source_type == "BESS":
            self.model = SistemaBESS()
        elif self.source_type == "DIESEL":
            self.model = SistemaDiesel()
        elif self.source_type == "DEMANDA":
            self.model = SistemaDemanda()
        else:
            raise ValueError(f"Tipo de fuente desconocido: {source_type}")

    def step(self, V_pcc=400.0, Q_ref=0.0):
        """Ejecuta un paso dinámico (500 ms) alimentado con datos sintéticos."""
        # 1. Cargar datos de entrada según el tipo de fuente
        if self.source_type == "SOLAR":
            poa, temp = self.data_loader.get_solar_at(self.step_index)
            self.model.POA = poa
            self.model.Tam = temp
        elif self.source_type == "EOLICA":
            ws = self.data_loader.get_eolic_at(self.step_index)
            self.model.Ws = ws
        elif self.source_type == "HIDRICA":
            vc = self.data_loader.get_hydro_at(self.step_index)
            self.model.Vc = vc

        # 2. Ejecutar integración física
        setpoints = {"Q_ref_kvar": Q_ref / 1000.0}
        ctx = self.model.step(dt=0.001, V_pcc=V_pcc, setpoints=setpoints)

        self.step_index += 1

        # Mapeo explícito de claves de potencia activa por tipo de fuente.
        # Evita el fallback genérico a "P_array" (clave exclusiva de Solar)
        # que enmascararía fallos físicos en otros tipos de nodo.
        _P_KEYS = {
            "SOLAR":   ["Pw", "P_array"],
            "EOLICA":  ["Pw", "Pm"],
            "HIDRICA": ["Pw", "Pm"],
            "BESS":    ["Pw", "P_bat"],
            "DIESEL":  ["Pw"],
            "DEMANDA": ["Pw"],
        }
        p_keys = _P_KEYS.get(self.source_type, ["Pw"])
        P_w = 0.0
        for key in p_keys:
            if key in ctx:
                P_w = ctx[key]
                break

        # Q_var: usar 0.0 como neutral seguro si el contexto no la reporta
        Q_var = ctx.get("Pq", 0.0)

        return {
            "node_id": self.node_id,
            "source_type": self.source_type,
            "step": self.step_index,
            "P_w": round(P_w, 2),
            "Q_var": round(Q_var, 2)
        }


if __name__ == "__main__":
    proc = NodeDynamicProcess(node_id=2, source_type="SOLAR")
    out = proc.step(V_pcc=400.0, Q_ref=1000.0)
    print(f"Prueba Nodo 2 Dinámica Solar: P = {out['P_w']} W, Q = {out['Q_var']} VAR")
