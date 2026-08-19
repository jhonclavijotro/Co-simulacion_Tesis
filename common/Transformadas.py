import math

class Transformadas:
    """Transformadas dq0, abc y sincronización PLL."""
    def __init__(self):
        self.theta = 0.0

    def abc_to_dq0(self, Va, Vb, Vc, theta):
        Vd = (2/3) * (Va * math.cos(theta) + Vb * math.cos(theta - 2*math.pi/3) + Vc * math.cos(theta + 2*math.pi/3))
        Vq = (2/3) * (-Va * math.sin(theta) - Vb * math.sin(theta - 2*math.pi/3) - Vc * math.sin(theta + 2*math.pi/3))
        return Vd, Vq, 0.0

    def dq0_to_abc(self, Vd, Vq, V0, theta):
        Va = Vd * math.cos(theta) - Vq * math.sin(theta)
        Vb = Vd * math.cos(theta - 2*math.pi/3) - Vq * math.sin(theta - 2*math.pi/3)
        Vc = Vd * math.cos(theta + 2*math.pi/3) - Vq * math.sin(theta + 2*math.pi/3)
        return Va, Vb, Vc

    def aplicar_transformadas(self, V_abc, Vqi=0.0):
        Va, Vb, Vc = V_abc
        Valpha = (2/3) * (Va - 0.5 * Vb - 0.5 * Vc)
        Vbeta = (2/3) * (math.sqrt(3)/2 * Vb - math.sqrt(3)/2 * Vc)
        Vd, Vq, V0 = self.abc_to_dq0(Va, Vb, Vc, self.theta)
        theta0 = self.theta
        Fsys = 60.0
        return Valpha, Vbeta, theta0, Vq, Vd, Fsys
