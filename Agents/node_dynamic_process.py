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
    def __init__(self, node_id, source_type="SOLAR", hold_mode="ZOH", zfoh_lambda=0.7):
        self.node_id = node_id
        self.source_type = source_type.upper()
        self.hold_mode = hold_mode.upper()
        self.zfoh_lambda = float(zfoh_lambda)
        self.V_pcc_prev = None
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

    def step_macro(self, V_pcc=400.0, Q_ref=0.0, macro_dt=0.5, micro_dt=0.001, hold_mode=None, zfoh_lambda=None):
        """
        Ejecuta un macro-paso de co-simulación (H = 500 ms) compuesto por 500 micro-pasos (h = 1 ms).
        
        Esquemas de Reconstrucción de Señal (Hold):
          - ZOH:  V_step(i) = V_pcc (constante a tramos, O(H))
          - FOH:  V_step(i) = V_pcc + dV/dt * (i * h) (lineal a tramos, O(H^2))
          - ZFOH: V_step(i) = V_pcc + lambda * dV/dt * (i * h) (combinación convexa, lambda in [0, 1])
        """
        active_hold = (hold_mode or self.hold_mode).upper()
        active_lambda = float(zfoh_lambda if zfoh_lambda is not None else self.zfoh_lambda)

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

        # 2. Inicialización de memoria de extrapolación para paso 0 (flat start)
        if self.V_pcc_prev is None:
            self.V_pcc_prev = float(V_pcc)

        # Cálculo de la tasa de cambio de tensión en el macro-paso
        dV_dt = (float(V_pcc) - self.V_pcc_prev) / float(macro_dt) if macro_dt > 0 else 0.0

        # 3. Ejecutar integración física de 500 micro-pasos (1 kHz) con reconstrucción de señal
        n_substeps = max(1, int(round(macro_dt / micro_dt)))
        setpoints = {"Q_ref_kvar": Q_ref / 1000.0}
        ctx = None

        for i in range(n_substeps):
            t_sub = i * micro_dt
            if active_hold == "FOH":
                V_sub = float(V_pcc) + dV_dt * t_sub
            elif active_hold == "ZFOH":
                V_sub = float(V_pcc) + active_lambda * dV_dt * t_sub
            else:  # ZOH por defecto
                V_sub = float(V_pcc)

            ctx = self.model.step(dt=micro_dt, V_pcc=V_sub, setpoints=setpoints)

        # Actualizar memoria de tensión previa para el próximo macro-paso
        self.V_pcc_prev = float(V_pcc)
        self.step_index += 1

        # Mapeo explícito de claves de potencia activa por tipo de fuente.
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
        if ctx:
            for key in p_keys:
                if key in ctx:
                    P_w = ctx[key]
                    break

        # Q_var: usar 0.0 como neutral seguro si el contexto no la reporta
        Q_var = ctx.get("Pq", 0.0) if ctx else 0.0

        return {
            "node_id": self.node_id,
            "source_type": self.source_type,
            "step": self.step_index,
            "P_w": round(P_w, 2),
            "Q_var": round(Q_var, 2)
        }

    def step(self, V_pcc=400.0, Q_ref=0.0):
        """Alias retrocompatible para ejecutar un macro-paso de co-simulación."""
        return self.step_macro(V_pcc=V_pcc, Q_ref=Q_ref, macro_dt=0.5, micro_dt=0.001)


if __name__ == "__main__":
    proc = NodeDynamicProcess(node_id=2, source_type="SOLAR")
    out = proc.step(V_pcc=400.0, Q_ref=1000.0)
    print(f"Prueba Nodo 2 Dinámica Solar: P = {out['P_w']} W, Q = {out['Q_var']} VAR")
