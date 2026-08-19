import csv
import numpy as np
from Eolica.Aerogenerador import Aerogenerador
from common.Transformadas import Transformadas
from common.RedTrifasica import RedTrifasica
from common.GridInverter import GridConnectedInverter
try:
    from common.GraficadorEolico import graficar_resultados
except ImportError:
    def graficar_resultados(): pass


class SistemaEolico:
    """Sistema eolico como fuente equivalente conectada a red.

    Modela el conjunto turbina+PMSG+rectificador como una fuente
    de corriente DC (Iwind) que alimenta el bus, similar al Boost
    solar. El GridInverter regula Vdc e inyecta potencia a la red.

    Dinamica:
      - La velocidad del rotor Wr sigue al target MPPT con lag de 1er orden
      - Pm = 0.5*rho*A*Cp(lambda)*V^3
      - Pgen = Pm * eta  (perdidas generador+rectificador)
      - Iwind = Pgen / Vdc
      - Vdc = integral((Iwind - Iinv_dc) / C_dc)
    """

    def __init__(self, R=2.5, B=8.0, relacion=4.0, eta=0.95):
        self.aerogenerador = Aerogenerador(R, B)
        self.relacion = relacion
        self.eta = eta
        self.C_dc = 0.001
        self.tau_Wr = 5.0
        self._vdc_int = 0.0
        self._Kp_vdc = 0.5
        self._Ki_vdc = 0.1
        self.redtrifasica = RedTrifasica()
        self.transformadas = Transformadas()
        self.inversor = GridConnectedInverter()
        self.datos = []
        self.sample_time = 0.001
        self.Ws = None
        self.contexto = {
            "time": 0.0,
            "Wr": 0.5,
            "Ws": 14.0,
            "Idi": 0.0,
            "Iq": 0.0,
            "Vqi": 0.0,
            "theta0": 0.0,
            "Vdi": 0.0,
            "Fsys": 0.0,
            "Vq": 0.0,
            "Tm": 0.0,
            "Pm": 0.0,
            "Wg": 0.0,
            "Vdc": 300.0,
            "Pdc_in": 0.0,
            "Pdc_out": 0.0,
            "Vdt": 0.0,
            "Cp": 0.0,
            "lambda": 0.0,
            "Iwind": 0.0,
        }

    def _perfil_viento(self, t):
        if t < 4:
            return 8.0
        elif t < 9:
            return 8.0 + (12.0 - 8.0) * ((t - 4) / 5.0)
        elif t < 10:
            return 12.0 - (12.0 - 10.0) * ((t - 9.9) / 1.0)
        elif t < 15:
            return 10.0
        elif t < 20:
            return 10.0 + (12.0 - 10.0) * ((t - 15) / 5.0)
        else:
            return 12.0

    def mppt(self, Ws):
        lambd_opt = 6.85
        R = 2.5
        return (Ws * lambd_opt) / R

    def _Cp(self, lambd, beta):
        c1, c2, c3, c4, c5, c6 = 0.5176, 116.0, 0.4, 5.0, 21.0, 0.0068
        inv = 1.0 / (lambd + 0.08 * beta) - 0.035 / (beta**3 + 1.0)
        x = 1.0 / inv if inv != 0 else 1e6
        cp = c1 * (c2 / x - c3 * beta - c4) * np.exp(-c5 / x) + c6 * lambd
        return max(cp, 0.0)

    def step(self, dt=0.001, V_pcc=None, setpoints=None):
        ctx = self.contexto

        if setpoints and "Q_ref_kvar" in setpoints:
            ctx["Pq"] = setpoints["Q_ref_kvar"] * 1000.0

        Ws = self.Ws if self.Ws is not None else self._perfil_viento(ctx["time"])
        ctx["Ws"] = Ws

        Wr_target = self.mppt(Ws)
        tau_inv = 1.0 / self.tau_Wr
        ctx["Wr"] = ctx["Wr"] + tau_inv * (Wr_target - ctx["Wr"]) * dt
        ctx["Wr"] = max(0.5, ctx["Wr"])
        ctx["Wg"] = ctx["Wr"] * self.relacion

        lambd = (self.aerogenerador.R * ctx["Wr"]) / max(Ws, 0.1)
        ctx["lambda"] = lambd
        cp = self._Cp(lambd, self.aerogenerador.B)
        ctx["Cp"] = cp

        area = np.pi * self.aerogenerador.R ** 2
        Pm = 0.5 * self.aerogenerador.rho * area * (Ws ** 3) * cp
        ctx["Pm"] = Pm

        Pgen = Pm * self.eta
        ctx["Pdc_in"] = Pgen

        Iwind = Pgen / max(ctx["Vdc"], 1.0)
        ctx["Iwind"] = Iwind

        error_vdc = self.inversor.Vdcref - ctx["Vdc"]
        self._vdc_int += error_vdc * self._Ki_vdc * dt
        self._vdc_int = max(-10.0, min(10.0, self._vdc_int))
        Iinv_cmd = Iwind - (self._Kp_vdc * error_vdc + self._vdc_int)
        Iinv_cmd = max(0.0, Iinv_cmd)

        Pw, Pq, _, Iqi, Vdt, Idiref = self.inversor.step(
            ctx["Vdc"], ctx["Vdi"], ctx["Vqi"], ctx["theta0"], Iinv_cmd, dt, D=0.0)

        Iinv_dc = Iinv_cmd
        ctx["Idi"] = self.inversor.Idi
        ctx["Iqi"] = Iqi
        ctx["Vdt"] = Vdt
        ctx["Pw"] = Pw
        ctx["Pq"] = Pq
        ctx["Pdc_out"] = ctx["Vdc"] * Iinv_cmd

        ic = Iwind - Iinv_dc
        ctx["Vdc"] = max(250.0, min(ctx["Vdc"] + (ic / self.C_dc) * dt, 450.0))

        if V_pcc is not None:
            Va, Vb, Vc = V_pcc, 0.0, 0.0
        else:
            Va, Vb, Vc = self.redtrifasica.step(ctx["time"], Pw, Pq)

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
                    res["time"], res["Wr"], res["Tm"], res["Wg"],
                    0, 0, res["Iwind"], res["Vdc"],
                    res["Pdc_in"], res["Vdt"], res["Idi"],
                    res.get("Idiref", 0), res["Pdc_out"],
                    res["Vdi"], res["Vqi"], res["Fsys"],
                    res["Pw"], res["Pq"], res["Ws"],
                    res["Vdi"], res["Vqi"], res["Fsys"],
                    res.get("Valpha", 0), res.get("Vbeta", 0),
                    res["lambda"], res["Cp"], res["Pm"],
                ])
            except Exception as e:
                print(f"Error: {e}")
                break

        header = ["Tiempo", "Wr", "Tm", "Wg", "Tg",
                  "Vq", "Iq", "Vdc", "Pdc_in",
                  "Vdt", "Idi", "Idiref", "Pdc_out",
                  "Vd_red", "Vq_red", "Fsys_red", "Pw", "Pq", "Ws",
                  "Va", "Vb", "Vc", "Valpha", "Vbeta",
                  "Lambda", "Cp", "Pm"]
        with open("resultados.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(self.datos)

        graficar_resultados()


if __name__ == "__main__":
    SistemaEolico().ejecutar()
