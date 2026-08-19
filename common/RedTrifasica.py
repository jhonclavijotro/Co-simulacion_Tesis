import math

class RedTrifasica:
    """Simulador de Tensión Trifásica de Red AC."""
    def __init__(self, V_rms=230.0, freq=60.0):
        self.V_rms = V_rms
        self.V_peak = V_rms * math.sqrt(2)
        self.freq = freq

    def get_voltages(self, t):
        w = 2 * math.pi * self.freq
        Va = self.V_peak * math.sin(w * t)
        Vb = self.V_peak * math.sin(w * t - 2*math.pi/3)
        Vc = self.V_peak * math.sin(w * t + 2*math.pi/3)
        return Va, Vb, Vc
