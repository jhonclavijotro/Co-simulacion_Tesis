import numpy as np


class Transformadas:
    def __init__(self):
        self.ylf1 = 0
        self.theta1 = 0
        self.Fsys1 = 0
        self.Vq1 = 0

    def aplicar_transformadas(self, cosenos, Vqi):
        Valpha_raw, Vbeta_raw = self.clarke(cosenos[0], cosenos[1], cosenos[2])
        Valpha = Valpha_raw
        Vbeta = Vbeta_raw

        ylf = self.lpf(Vqi, self.Vq1, self.ylf1)
        self.Vq1 = Vqi
        self.ylf1 = ylf

        fn = 60
        delta_t = 0.001
        theta0, fo = self.VCO(fn, ylf, delta_t, self.theta1)
        self.theta1 = theta0

        Vd_out, Vq_out = self.park(Valpha_raw, Vbeta_raw, theta0)

        Fsys = self.filtro(fo, self.Fsys1)
        self.Fsys1 = Fsys

        return Valpha, Vbeta, theta0, Vq_out, Vd_out, Fsys

    def clarke(self, Va, Vb, Vc):
        Valpha = (2 * Va - Vb - Vc) / 3
        Vbeta = (Vb - Vc) / np.sqrt(3)
        return [Valpha, Vbeta]

    def park(self, Valpha, Vbeta, theta):
        Vd = Valpha * np.cos(theta) + Vbeta * np.sin(theta)
        Vq = -Valpha * np.sin(theta) + Vbeta * np.cos(theta)
        return [Vd, Vq]

    def lpf(self, Vq, Vq1, ylf1):
        ylf = ylf1 + (1.92 * Vq) - (1.7 * Vq1)
        return ylf

    def VCO(self, fn, ylf, delta_t, theta1):
        fo = fn + ylf
        theta0 = theta1 + (fo * delta_t * 6.2831852)
        if theta0 > 6.2831852:
            theta0 -= 6.2831852
        return theta0, fo

    def filtro(self, Fsys, Fsys1):
        alpha = 0.9
        return alpha * Fsys + (1 - alpha) * Fsys1
