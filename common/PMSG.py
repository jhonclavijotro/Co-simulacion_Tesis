import numpy as np
from scipy import signal


class PMSG:
    def __init__(self, metodo="euler"):
        self.Rs = 0.075
        self.Ls = 1.25e-3
        self.Fm = 0.1666
        self.Jr = 0.0008
        self.Kb = 0.0001
        self.P = 4
        self.metodo = metodo
        self.Iq = 0.0
        self.Wg = 0.0

    def calcular_respuesta(self, Vq, Tm, t_sample):
        if self.metodo == "euler":
            return self._calcular_euler(Vq, Tm, t_sample)
        else:
            return self._calcular_statespace(Vq, Tm, t_sample)

    def _calcular_euler(self, Vq, Tm, t_sample):
        dIq_dt = (-self.Rs * self.Iq / self.Ls
                  - self.Fm * self.P * self.Wg / self.Ls
                  + Vq / self.Ls)
        dWg_dt = (1.5 * self.Fm * self.P * self.Iq / self.Jr
                  - self.Kb * self.Wg / self.Jr
                  - Tm / self.Jr)
        self.Iq += dIq_dt * t_sample
        self.Wg += dWg_dt * t_sample
        return self.Iq, self.Wg

    def _calcular_statespace(self, Vq, Tm, t_sample):
        A = np.array([[-self.Rs / self.Ls, -self.Fm * self.P / self.Ls],
                      [1.5 * self.Fm * self.P / self.Jr, -self.Kb / self.Jr]])
        B = np.array([[Vq / self.Ls], [-Tm / self.Jr]])
        C = np.eye(2)
        D = np.zeros((2, 1))
        sys = signal.StateSpace(A, B, C, D)
        sys_disc = sys.to_discrete(t_sample)
        result = signal.dstep(sys_disc)
        y_out = result[1]
        y_array = np.squeeze(y_out[0])
        Iq = y_array[-1, 0]
        Wg = y_array[-1, 1]
        self.Iq = Iq
        self.Wg = Wg
        return Iq, Wg


class Gearbox:
    def __init__(self, relacion_transmision):
        self.relacion = relacion_transmision

    def convertir_torque_velocidad(self, Tm, Wg):
        wr = Wg / self.relacion
        Tg = Tm / self.relacion
        return Tg, wr


class SistemaPMG:
    def __init__(self, relacion_transmision, metodo="euler"):
        self.pmsg = PMSG(metodo=metodo)
        self.gearbox = Gearbox(relacion_transmision)

    def calcular_sistema(self, Vq, Tm, t_sample):
        Iq, Wg = self.pmsg.calcular_respuesta(Vq, Tm, t_sample)
        Te = 1.5 * self.pmsg.Fm * self.pmsg.P * Iq
        Tg, Wr = self.gearbox.convertir_torque_velocidad(Tm, Wg)
        return {"Iq": Iq, "Wg": Wg, "Te": Te, "Tg": Tg, "Wr": Wr}

    @property
    def Fm(self):
        return self.pmsg.Fm

    @property
    def P(self):
        return self.pmsg.P
