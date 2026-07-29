class BuckBoost:
    """Convertidor DC-DC bidireccional - modelo promedio energetico.

    Modela el convertidor como un lazo de primer orden entre la
    corriente de bateria y su referencia, con balance de potencia
    ideal en el bus DC:

      tau * dI_bat/dt = I_bat_ref - I_bat
      I_dc = V_bat * I_bat / Vdc  (balance de potencia, sin perdidas)

    El control de corriente usa un PI con anti-windup por integracion
    condicional (conditional integration): el integrador se congela
    cuando el duty alcanza la saturacion y el error tiende a aumentarla.

    Esto es numericamente estable para cualquier paso de tiempo y
    evita los problemas de signo de las ecuaciones conmutadas.
    """

    def __init__(self, tau=0.01, Kp=0.1, Ki=0.5, d_min=-0.9, d_max=0.9):
        self.C_dc = 2000e-6
        self.tau = tau
        self.Vdc = 400.0
        self.I_bat = 0.0
        self.Kp = Kp
        self.Ki = Ki
        self.d_min = d_min
        self.d_max = d_max
        self.integral = 0.0

    def calcular_referencia_corriente(self, P_ref, V_bat):
        if abs(V_bat) < 1.0:
            return 0.0
        return P_ref / V_bat

    def control_corriente(self, I_bat_ref, I_bat_actual, dt=0.001):
        error = I_bat_ref - I_bat_actual

        u = self.Kp * error + self.Ki * self.integral
        u_sat = max(self.d_min, min(self.d_max, u))

        if abs(u_sat) < self.d_max or error * u_sat <= 0:
            self.integral += error * dt

        return u_sat

    def reset_integral(self):
        self.integral = 0.0

    def actualizar_estado(self, duty, I_bat_ref, V_bat, Vdc, I_inv, dt):
        alpha = min(1.0, dt / self.tau)
        self.I_bat += (I_bat_ref - self.I_bat) * alpha

        I_dc = V_bat * self.I_bat / max(Vdc, 1.0)

        dVdc = (I_dc - I_inv) / self.C_dc
        Vdc += dVdc * dt

        self.Vdc = max(360.0, min(Vdc, 440.0))
        return self.I_bat, self.Vdc
