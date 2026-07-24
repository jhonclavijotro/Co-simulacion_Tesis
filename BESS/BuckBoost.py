class BuckBoost:
    """Convertidor DC-DC bidireccional - modelo promedio energetico.

    Modela el convertidor como un lazo de primer orden entre la
    corriente de bateria y su referencia, con balance de potencia
    ideal en el bus DC:

      tau * dI_bat/dt = I_bat_ref - I_bat
      I_dc = V_bat * I_bat / Vdc  (balance de potencia, sin perdidas)

    Esto es numericamente estable para cualquier paso de tiempo y
    evita los problemas de signo de las ecuaciones conmutadas.
    """

    def __init__(self, tau=0.01):
        self.C_dc = 2000e-6
        self.tau = tau
        self.Vdc = 400.0
        self.I_bat = 0.0

    def calcular_referencia_corriente(self, P_ref, V_bat):
        if abs(V_bat) < 1.0:
            return 0.0
        return P_ref / V_bat

    def control_corriente(self, I_bat_ref, I_bat_actual, Kp=0.1):
        error = I_bat_ref - I_bat_actual
        return max(-0.9, min(0.9, Kp * error))

    def actualizar_estado(self, duty, I_bat_ref, V_bat, Vdc, I_inv, dt):
        alpha = min(1.0, dt / self.tau)
        self.I_bat += (I_bat_ref - self.I_bat) * alpha

        I_dc = V_bat * self.I_bat / max(Vdc, 1.0)

        dVdc = (I_dc - I_inv) / self.C_dc
        Vdc += dVdc * dt

        self.Vdc = max(360.0, min(Vdc, 440.0))
        return self.I_bat, self.Vdc
