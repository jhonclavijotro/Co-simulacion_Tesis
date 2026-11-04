import sys
import os
import time
import math

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

    Esquemas de Reconstrucción de Señal en Frontera Multitasa:
      - ZOH (Zero-Order Hold): V_sub(t) = V(k). Esquema canónico por defecto (óptimo en lazo cerrado).
      - FOH (First-Order Hold): V_sub(t) = V(k) + (dV/dt) * t_sub.
      - FROH (Fractional-Order Hold): V_sub(t) = V(k) + lambda * (dV/dt) * t_sub con lambda in [0, 1].
        NOTA TECNICA (S-24): Opera como un PREDICTOR/EXTRAPOLADOR hacia adelante basado en la
        diferencia finita hacia atrás (V(k) - V(k-1))/H. No es una interpolación causal entre V(k) y V(k+1)
        (tipo Ishitobi). En perfiles de recuperación exponencial tras perturbaciones (convexas),
        sobreestima la derivada actual acumulando error en nodos solares sensibles (3.72x peor que ZOH a lambda=0.7).
        Acepta 'ZFOH' y 'zfoh_lambda' como alias retrocompatibles.
    """
    def __init__(self, node_id, source_type="SOLAR", hold_mode="ZOH", froh_lambda=0.7, zfoh_lambda=None):
        self.node_id = node_id
        self.source_type = source_type.upper()
        h_mode = hold_mode.upper()
        self.hold_mode = "FROH" if h_mode == "ZFOH" else h_mode
        self.froh_lambda = float(zfoh_lambda if zfoh_lambda is not None else froh_lambda)
        self.zfoh_lambda = self.froh_lambda  # Alias retrocompatible
        self.V_pcc_prev = None
        self.data_loader = MockDataLoader()
        self.step_index = 0

        # Inicialización del modelo dinámico con capacidades para microrred de baja potencia
        if self.source_type == "SOLAR":
            self.model = SistemaSolar(N_inv=2)
        elif self.source_type == "EOLICA":
            self.model = SistemaEolico()
        elif self.source_type == "HIDRICA":
            self.model = SistemaHidrico()
        elif self.source_type == "BESS":
            # droop_enabled=False: el control de despacho y droop secundario se gobierna
            # en el agente MAS (distributed_node_runner) evitando saturacion bang-bang
            self.model = SistemaBESS(N_inv=1, droop_enabled=False)
        elif self.source_type == "DIESEL":
            self.model = SistemaDiesel(P_nominal=10000.0, droop_enabled=False)
        elif self.source_type == "DEMANDA":
            self.model = SistemaDemanda()
        else:
            raise ValueError(f"Tipo de fuente desconocido: {source_type}")

    def step_macro(self, V_pcc=400.0, Q_ref=0.0, P_ref=0.0, delta_P=0.0, delta_omega=0.0,
                   macro_dt=0.5, micro_dt=0.001, hold_mode=None, froh_lambda=None, zfoh_lambda=None):
        """
        Ejecuta un macro-paso de co-simulación (H = 500 ms) compuesto por 500 micro-pasos (h = 1 ms).
        
        Esquemas de Reconstrucción de Señal (Hold):
          - ZOH:  V_step(i) = V_pcc (constante a tramos, O(H)) - CANONICO POR DEFECTO
          - FOH:  V_step(i) = V_pcc + dV/dt * (i * h) (lineal a tramos, O(H^2))
          - FROH: V_step(i) = V_pcc + lambda * dV/dt * (i * h) (predictor hacia adelante, lambda in [0, 1])
                  (Acepta 'ZFOH' y 'zfoh_lambda' como alias retrocompatibles).
        """
        req_hold = (hold_mode or self.hold_mode).upper()
        active_hold = "FROH" if req_hold == "ZFOH" else req_hold
        eff_lambda = froh_lambda if froh_lambda is not None else (zfoh_lambda if zfoh_lambda is not None else self.froh_lambda)
        active_lambda = float(eff_lambda)

        # Detección heurística de escala de tensión (MT > 1kV -> 13.8kV, BT > 10V -> 400V, else pu)
        v_num = float(V_pcc)
        if v_num > 1000.0:
            v_pu = v_num / 13800.0
        elif v_num > 10.0:
            v_pu = v_num / 400.0
        else:
            v_pu = v_num
        v_inv_terminal = v_pu * 110.0

        # 1. Cargar datos de entrada según el tipo de fuente
        if self.source_type == "SOLAR":
            try:
                poa, temp = self.data_loader.get_solar_at(self.step_index)
            except Exception:
                poa, temp = 1000.0, 298.15
            self.model.POA = poa
            self.model.Tam = temp
        elif self.source_type == "EOLICA":
            try:
                ws = self.data_loader.get_eolic_at(self.step_index)
            except Exception:
                ws = 10.0
            self.model.Ws = ws
        elif self.source_type == "HIDRICA":
            try:
                vc = self.data_loader.get_hydro_at(self.step_index)
            except Exception:
                vc = 1.5
            self.model.Vc = vc

        # 2. Inicialización de memoria de extrapolación para paso 0 (flat start)
        if self.V_pcc_prev is None:
            self.V_pcc_prev = float(v_inv_terminal)

        # Cálculo de la tasa de cambio de tensión en el macro-paso
        dV_dt = (float(v_inv_terminal) - self.V_pcc_prev) / float(macro_dt) if macro_dt > 0 else 0.0

        # 3. Ejecutar integración física por n_substeps (macro_dt / micro_dt) con reconstrucción de señal
        n_substeps = max(1, int(round(macro_dt / micro_dt)))
        setpoints = {
            "Q_ref_kvar": Q_ref / 1000.0,
            "P_ref": P_ref,
            "P_ref_w": P_ref,
            "delta_P": delta_P,
            "delta_omega": delta_omega
        }
        ctx = None

        for i in range(n_substeps):
            t_sub = i * micro_dt
            if active_hold == "FOH":
                V_sub = float(v_inv_terminal) + dV_dt * t_sub
            elif active_hold in ["FROH", "ZFOH"]:
                # Predictor/extrapolador hacia adelante con ganancia fraccional lambda
                V_sub = float(v_inv_terminal) + active_lambda * dV_dt * t_sub
            else:  # ZOH por defecto canónico
                V_sub = float(v_inv_terminal)

            ctx = self.model.step(dt=micro_dt, V_pcc=V_sub, setpoints=setpoints)

        # Actualizar memoria de tensión previa para el próximo macro-paso
        self.V_pcc_prev = float(v_inv_terminal)
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
        Fsys = ctx.get("Fsys", 60.0) if ctx else 60.0
        omega_i = 2.0 * math.pi * Fsys

        # Determinación de P_max disponible para el agente MAS
        P_max = 10000.0
        if ctx and "P_max" in ctx:
            P_max = float(ctx["P_max"])
        elif hasattr(self.model, "P_disponible"):
            P_max = float(self.model.P_disponible)
        elif hasattr(self.model, "P_nominal"):
            P_max = float(self.model.P_nominal)
        elif self.source_type == "SOLAR":
            P_max = 5000.0
        elif self.source_type == "BESS":
            P_max = 3000.0
        
        P_ratio = (P_w / P_max) if P_max > 0 else 0.0

        return {
            "node_id": self.node_id,
            "source_type": self.source_type,
            "step": self.step_index,
            "P_w": round(P_w, 2),
            "Q_var": round(Q_var, 2),
            "Fsys": round(Fsys, 4),
            "omega": round(omega_i, 4),
            "P_max": round(P_max, 2),
            "P_ratio": round(P_ratio, 4)
        }

    def step(self, V_pcc=400.0, Q_ref=0.0, P_ref=0.0, delta_P=0.0, delta_omega=0.0):
        """Alias retrocompatible para ejecutar un macro-paso de co-simulación."""
        return self.step_macro(V_pcc=V_pcc, Q_ref=Q_ref, P_ref=P_ref, delta_P=delta_P, delta_omega=delta_omega, macro_dt=0.5, micro_dt=0.001)


if __name__ == "__main__":
    proc = NodeDynamicProcess(node_id=2, source_type="SOLAR")
    out = proc.step(V_pcc=400.0, Q_ref=1000.0)
    print(f"Prueba Nodo 2 Dinámica Solar: P = {out['P_w']} W, Q = {out['Q_var']} VAR")
