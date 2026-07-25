import numpy as np
from scipy import signal


class Rectificador:
    def __init__(self):
        self.E1_prev = 0.0
        self.y10_prev = 0.0
        self.E2_prev = 0.0
        self.y2_prev = 0.0
        self.E4_prev = 0.0
        self.y3_prev = 0.0
        self.Id = 0.0
        self.Vdv = []
        self.Vqv = []
        self.Vdcv = []

    def mppt(self, Ws):
        lambdaop = 6.85
        return (Ws * (lambdaop / 2.15)) * 3

    def control(self, error, error_prev, y_prev):
        return 0.02 * error + 0.08 * error_prev + y_prev

    def control2(self, error, error_prev, y_prev):
        return 0.08 * error + 0.2 * error_prev + y_prev

    def decoupledC(self, Md, Mq, Wg, Id, Iq):
        Ls = 5e-3
        Ud = Md - (Iq * Wg * Ls)
        Uq = Mq + (Id * Wg * Ls)
        return Ud, Uq

    def PlantaRC(self, ic, t_sample, Vdc_current):
        C = 0.001
        Vdc_new = Vdc_current + (ic / C) * t_sample
        return max(250, min(Vdc_new, 450))

    def ejecutar(self, Ws, Wr, Iq, Idi, Wg, Vdc, t_sample):
        Wref = self.mppt(Ws)
        E = Wref - Wr
        Iqref = self.control(E, self.E1_prev, self.y10_prev)
        self.E1_prev, self.y10_prev = E, Iqref

        Idref = 0.0
        E2 = Idref - self.Id
        Md = self.control2(E2, self.E2_prev, self.y2_prev)
        self.E2_prev, self.y2_prev = E2, Md

        E4 = Iqref - Iq
        Mq = self.control2(E4, self.E4_prev, self.y3_prev)
        self.E4_prev, self.y3_prev = E4, Mq

        Vd_rect, Vq_rect = self.decoupledC(Md, Mq, Wg, self.Id, Iq)
        self.Vdv.append(Vd_rect)
        self.Vqv.append(Vq_rect)

        ic_actual = Iq - Idi
        Vdc_new = self.PlantaRC(ic_actual, t_sample, Vdc)
        self.Vdcv.append(Vdc_new)

        Pdc_in = Vdc_new * Iq
        Pdc_out = Vdc_new * Idi

        return Vdc_new, Vq_rect, Pdc_in, Pdc_out
