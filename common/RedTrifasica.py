import numpy as np
from common.Transformadas import Transformadas


class RedTrifasica:
    def __init__(self, v_nominal=110.0, f_nominal=60.0):
        self.v_nominal = v_nominal
        self.f_nominal = f_nominal
        self.amplitud = v_nominal
        self.frecuencia = f_nominal
        self.net_active = 0.0
        self.net_reactive = 0.0
        self.k_f = 0.01
        self.k_v = 0.05
        self.pll = Transformadas()
        self.Vq_prev_pll = 0.0

    def actualizar_droop(self):
        self.frecuencia = self.f_nominal - self.k_f * (self.net_active / 1000.0)
        self.amplitud = self.v_nominal - self.k_v * (self.net_reactive / 1000.0)

    def generar_senal_trifasica(self, t):
        w = 2 * np.pi * self.frecuencia
        va = self.amplitud * np.cos(w * t)
        vb = self.amplitud * np.cos(w * t - 2 * np.pi / 3)
        vc = self.amplitud * np.cos(w * t - 4 * np.pi / 3)
        return va, vb, vc

    def step(self, t, Pw, Pq):
        self.inyectar_potencia(Pw, Pq)
        self.actualizar_droop()
        va, vb, vc = self.generar_senal_trifasica(t)
        Valpha, Vbeta, theta, Vq_out, Vd_out, Fsys = self.pll.aplicar_transformadas(
            [va, vb, vc], self.Vq_prev_pll
        )
        self.Vq_prev_pll = Vq_out
        return va, vb, vc

    def inyectar_potencia(self, potencia_activa, potencia_reactiva):
        self.net_active = potencia_activa
        self.net_reactive = potencia_reactiva
