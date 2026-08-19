import csv
import numpy as np
from Diesel.Diesel import MotorDiesel
from common.Transformadas import Transformadas
from common.GridInverter import GridConnectedInverter


class SistemaDiesel:
    """Sistema diesel como fuente equivalente conectada a red.

    Modela el motor diesel + PMSG + rectificador como fuente de
    corriente DC. El gobernador regula velocidad, el GridInverter
    regula Vdc e inyecta potencia a la red. V_pcc proviene del
    solver central (FBS).

    Dinamica:
      - Wm sigue a pref con lag de 1er orden (governor + inercia)
      - Gobernador PI: fuel = Kp*(pref-Wm) + integral
      - Motor 1er orden: Tm = lag(fuel) con te=0.035s
      - Pm = Tm * Wm
      - Idiesel = Pm * eta / Vdc
      - Vdc = integral((Idiesel - Iinv_dc) / C_dc)
    """

    def __init__(self, Kp_gov=0.001, Ki_gov=0.02, eta=0.95, tau_Wm=0.5):
        self.motor = MotorDiesel(Ke=1.0, te=0.035)
        self.eta = eta
        self.C_dc = 0.001
        self.tau_Wm = tau_Wm

        self._gov_int = 0.5
        self._Kp_gov = Kp_gov
        self._Ki_gov = Ki_gov

        self._vdc_int = 0.0
        self._Kp_vdc = 0.5
        self._Ki_vdc = 0.1

        self.inversor = GridConnectedInverter()
        self.transformadas = Transformadas()
        self.datos = []
        self.sample_time = 0.001
        self.pref = 188.5

        self.contexto = {
            "time": 0.0,
            "pref": 188.5,
            "Wm": 185.0,
            "Tm": 0.0,
            "Pm": 0.0,
            "Pgen": 0.0,
            "Idiesel": 0.0,
            "Vdc": 300.0,
            "Vdi": 0.0,
            "Vqi": 0.0,
            "theta0": 0.0,
            "Fsys": 0.0,
            "Pw": 0.0,
            "Pq": 0.0,
            "Idi": 0.0,
            "Iqi": 0.0,
            "Vdt": 0.0,
        }

    def step(self, dt=0.001, V_pcc=None, setpoints=None):
        ctx = self.contexto

        if setpoints:
            if "pref_ajuste" in setpoints:
                self.pref = setpoints["pref_ajuste"]
                ctx["pref"] = self.pref
            if "Q_ref_kvar" in setpoints:
                ctx["Pq"] = setpoints["Q_ref_kvar"] * 1000.0

        tau_inv = 1.0 / self.tau_Wm
        ctx["Wm"] = ctx["Wm"] + tau_inv * (self.pref - ctx["Wm"]) * dt
        ctx["Wm"] = max(50.0, ctx["Wm"])

        E = self.pref - ctx["Wm"]
        self._gov_int += E * self._Ki_gov * dt
        self._gov_int = max(-10.0, min(10.0, self._gov_int))
        F = self._Kp_gov * E + self._gov_int
        F = max(-10.0, min(10.0, F))

        Tm = self.motor.step(F, dt)
        ctx["Tm"] = Tm

        Pm = Tm * ctx["Wm"]
        ctx["Pm"] = Pm

        Pgen = Pm * self.eta
        ctx["Pgen"] = Pgen

        Idiesel = Pgen / max(ctx["Vdc"], 1.0)
        ctx["Idiesel"] = Idiesel

        error_vdc = self.inversor.Vdcref - ctx["Vdc"]
        self._vdc_int += error_vdc * self._Ki_vdc * dt
        self._vdc_int = max(-10.0, min(10.0, self._vdc_int))
        Iinv_cmd = Idiesel - (self._Kp_vdc * error_vdc + self._vdc_int)
        Iinv_cmd = max(0.0, Iinv_cmd)

        Pw, Pq, _, Iqi, Vdt, Idiref = self.inversor.step(
            ctx["Vdc"], ctx["Vdi"], ctx["Vqi"], ctx["theta0"], Iinv_cmd, dt, D=0.0)

        Iinv_dc = Iinv_cmd
        ctx["Idi"] = self.inversor.Idi
        ctx["Iqi"] = Iqi
        ctx["Vdt"] = Vdt
        ctx["Pw"] = Pw
        ctx["Pq"] = Pq

        ic = Idiesel - Iinv_dc
        ctx["Vdc"] = max(250.0, min(ctx["Vdc"] + (ic / self.C_dc) * dt, 450.0))

        if V_pcc is not None:
            Va, Vb, Vc = V_pcc
        else:
            Va, Vb, Vc = 0.0, 0.0, 0.0

        Valpha, Vbeta, theta0, Vq_out, Vd_out, Fsys = \
            self.transformadas.aplicar_transformadas([Va, Vb, Vc], ctx["Vqi"])
        ctx["theta0"] = theta0
        ctx["Vqi"] = Vq_out
        ctx["Vdi"] = Vd_out
        ctx["Fsys"] = Fsys

        ctx["time"] = round(ctx["time"] + dt, 3)
        return dict(ctx)

    def ejecutar(self, tiempo_simulacion=25):
        while self.contexto["time"] < tiempo_simulacion:
            try:
                res = self.step(self.sample_time)
                self.datos.append([
                    res["time"], res["pref"], res["Wm"], res["Tm"],
                    res["Pm"], res["Pgen"], res["Idiesel"], res["Vdc"],
                    res["Pw"], res["Pq"], res["Fsys"],
                    res["Idi"], res["Iqi"],
                ])
            except Exception as e:
                print(f"Error: {e}")
                break

        header = ["Tiempo", "Pref", "Wm", "Tm",
                   "Pm", "Pgen", "Idiesel", "Vdc",
                   "Pw", "Pq", "Fsys",
                   "Idi", "Iqi"]
        with open("resultados_diesel.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(self.datos)


if __name__ == "__main__":
    SistemaDiesel().ejecutar()
