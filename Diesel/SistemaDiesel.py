import csv
import numpy as np
from common.Transformadas import Transformadas
from common.GridInverter import GridConnectedInverter


class SistemaDiesel:
    """Sistema Diésel como convertidor de fuente de tensión (VSI-dq) conectado a red.

    Homogeneizado según las directrices de diseño de la microrred:
    Modela la generación Diésel mediante una fuente primaria de potencia activa
    acoplada a un bus DC y un inversor trifásico de fuente de tensión (VSI) en marco dq,
    sincronizado con la red mediante SRF-PLL.

    Esto unifica la API de simulación de los 5 nodos DER (Solar, Eólica, BESS, Hídrica, Diésel)
    eliminando modelos analógicos electromecánicos pesados no requeridos en inversores electrónicos.
    """

    def __init__(self, P_nominal=50000.0, Vdcref=400.0, eta=0.95, tau_P=0.05):
        """Inicializa el nodo Diésel homogeneizado como VSI-dq.

        Parámetros:
            P_nominal: Potencia activa nominal del grupo Diésel [W] (default: 50 kW).
            Vdcref:    Tensión de referencia del bus DC [V] (default: 400 V).
            eta:       Eficiencia de conversión global [0..1].
            tau_P:     Constante de tiempo de respuesta de potencia [s].
        """
        self.P_nominal = float(P_nominal)
        self.Vdcref = float(Vdcref)
        self.eta = float(eta)
        self.tau_P = float(tau_P)
        self.C_dc = 0.002

        # Lazo de regulación de Vdc
        self._vdc_int = 0.0
        self._Kp_vdc = 0.8
        self._Ki_vdc = 0.2

        self.inversor = GridConnectedInverter(Vdcref=self.Vdcref)
        self.transformadas = Transformadas()
        self.datos = []
        self.sample_time = 0.001
        self.pref = self.P_nominal  # Setpoint de potencia activa [W]

        self.contexto = {
            "time": 0.0,
            "pref": self.P_nominal,
            "P_gen": self.P_nominal,
            "Pm": self.P_nominal,
            "Pgen": self.P_nominal,
            "Idiesel": self.P_nominal / self.Vdcref,
            "Vdc": self.Vdcref,
            "Vdi": 230.0,
            "Vqi": 0.0,
            "theta0": 0.0,
            "Fsys": 60.0,
            "Pw": 0.0,
            "Pq": 0.0,
            "Idi": 0.0,
            "Iqi": 0.0,
            "Vdt": 0.0,
        }

    def step(self, dt=0.001, V_pcc=None, setpoints=None):
        """Ejecuta un micro-paso de integración física del convertidor VSI Diésel.

        Parámetros:
            dt:        Paso de integración [s] (default: 1 ms).
            V_pcc:     Tensión medida en el PCC [V o tupla (Va, Vb, Vc)].
            setpoints: Diccionario opcional de consignas (P_ref, Q_ref_kvar, etc.).
        """
        ctx = self.contexto

        # 1. Actualización de consignas exógenas
        if setpoints:
            if "pref_ajuste" in setpoints:
                self.pref = float(setpoints["pref_ajuste"])
                ctx["pref"] = self.pref
            elif "P_ref" in setpoints:
                self.pref = float(setpoints["P_ref"])
                ctx["pref"] = self.pref
            if "Q_ref_kvar" in setpoints:
                ctx["Pq"] = setpoints["Q_ref_kvar"] * 1000.0

        # 2. Dinámica de primer orden de entrega de potencia de la fuente primaria
        dP = (self.pref - ctx["P_gen"]) / max(1e-4, self.tau_P)
        ctx["P_gen"] = max(0.0, min(ctx["P_gen"] + dP * dt, self.P_nominal * 1.2))
        ctx["Pm"] = ctx["P_gen"]
        ctx["Pgen"] = ctx["P_gen"] * self.eta

        # 3. Corriente equivalente inyectada al bus DC
        v_dc_actual = max(100.0, ctx["Vdc"])
        Idiesel = ctx["Pgen"] / v_dc_actual
        ctx["Idiesel"] = Idiesel

        # 4. Control PI de regulación de tensión en bus DC
        error_vdc = self.Vdcref - v_dc_actual
        self._vdc_int += error_vdc * self._Ki_vdc * dt
        self._vdc_int = max(-20.0, min(20.0, self._vdc_int))
        Iinv_cmd = max(0.0, Idiesel - (self._Kp_vdc * error_vdc + self._vdc_int))

        # 5. Integración del Inversor VSI en marco dq
        Pw, Pq, _, Iqi, Vdt, Idiref = self.inversor.step(
            v_dc_actual, ctx["Vdi"], ctx["Vqi"], ctx["theta0"], Iinv_cmd, dt, D=0.0
        )

        ctx["Idi"] = self.inversor.Idi_ref
        ctx["Iqi"] = Iqi
        ctx["Vdt"] = Vdt
        ctx["Pw"] = Pw
        ctx["Pq"] = Pq

        # 6. Balance de carga en el capacitor del bus DC
        i_cap = Idiesel - Iinv_cmd
        ctx["Vdc"] = max(200.0, min(ctx["Vdc"] + (i_cap / self.C_dc) * dt, 600.0))

        # 7. Sincronización SRF-PLL con V_pcc
        if V_pcc is not None:
            if isinstance(V_pcc, (int, float)):
                Va, Vb, Vc = self.transformadas.synthesize_vabc(V_pcc)
            else:
                Va, Vb, Vc = V_pcc
        else:
            Va, Vb, Vc = self.transformadas.synthesize_vabc(230.0)

        Valpha, Vbeta, theta0, Vq_out, Vd_out, Fsys = \
            self.transformadas.aplicar_transformadas([Va, Vb, Vc], ctx["Vqi"])

        ctx["theta0"] = theta0
        ctx["Vqi"] = Vq_out
        ctx["Vdi"] = Vd_out
        ctx["Fsys"] = Fsys
        ctx["time"] = round(ctx["time"] + dt, 4)

        return dict(ctx)

    def ejecutar(self, tiempo_simulacion=5.0):
        """Ejecuta una simulación autónoma y guarda resultados en CSV."""
        while self.contexto["time"] < tiempo_simulacion:
            try:
                res = self.step(self.sample_time)
                self.datos.append([
                    res["time"], res["pref"], res["P_gen"],
                    res["Pgen"], res["Idiesel"], res["Vdc"],
                    res["Pw"], res["Pq"], res["Fsys"],
                    res["Idi"], res["Iqi"],
                ])
            except Exception as e:
                print(f"Error en simulación Diésel: {e}")
                break

        header = ["Tiempo", "Pref", "P_gen", "Pgen", "Idiesel", "Vdc",
                  "Pw", "Pq", "Fsys", "Idi", "Iqi"]
        with open("resultados_diesel.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(self.datos)


if __name__ == "__main__":
    diesel = SistemaDiesel(P_nominal=40000.0)
    for _ in range(100):
        out = diesel.step(dt=0.001, V_pcc=230.0)
    print(f"Prueba Diésel VSI-dq: Pw = {out['Pw']:.2f} W, Pq = {out['Pq']:.2f} VAR, Vdc = {out['Vdc']:.2f} V")
