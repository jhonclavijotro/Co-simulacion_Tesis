import numpy as np


class MotorDiesel:
    """Modelo de primer orden del motor Diesel con estado interno.

    Reemplaza la creacion de sistemas StateSpace en cada paso,
    manteniendo el estado del filtro digital recursivo.

    G(s) = Ke / (te*s + 1)
      y[n] = a*y[n-1] + b*u[n]
      a = exp(-dt/te), b = Ke*(1 - a)
    """

    def __init__(self, Ke=1.0, te=0.035):
        self.Ke = Ke
        self.te = te
        self.Tm = 0.0

    def step(self, F, dt):
        a = np.exp(-dt / self.te)
        b = self.Ke * (1.0 - a)
        self.Tm = a * self.Tm + b * F
        return self.Tm
