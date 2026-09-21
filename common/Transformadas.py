import math

class SRFPLL:
    """
    Phase-Locked Loop en Marco de Referencia Síncrono (SRF-PLL) discretizado.
    
    Implementación según estructura PI estándar (Teodorescu et al., 2011 / Kundu et al., 2024):
        - Clarke: abc -> alpha, beta
        - Park: alpha, beta -> d, q usando theta_hat
        - PI actúa sobre v_q para anular el error de fase
        - Integrador angular actualiza theta con omega_est
    """
    def __init__(self, f_nom=60.0, Kp_pll=94.25, Ki_pll=2220.0, Ts=0.001):
        self.omega_nom = 2.0 * math.pi * f_nom
        self.Kp = Kp_pll
        self.Ki = Ki_pll
        self.Ts = Ts
        
        # Estados internos
        self.theta = 0.0
        self.omega_est = self.omega_nom
        self._int_state = 0.0
        self.f_sys = f_nom

    def abc_to_dq0(self, Va, Vb, Vc, theta):
        Vd = (2.0/3.0) * (Va * math.cos(theta) + Vb * math.cos(theta - 2.0*math.pi/3.0) + Vc * math.cos(theta + 2.0*math.pi/3.0))
        Vq = (2.0/3.0) * (-Va * math.sin(theta) - Vb * math.sin(theta - 2.0*math.pi/3.0) - Vc * math.sin(theta + 2.0*math.pi/3.0))
        V0 = (1.0/3.0) * (Va + Vb + Vc)
        return Vd, Vq, V0

    def dq0_to_abc(self, Vd, Vq, V0, theta):
        Va = Vd * math.cos(theta) - Vq * math.sin(theta) + V0
        Vb = Vd * math.cos(theta - 2.0*math.pi/3.0) - Vq * math.sin(theta - 2.0*math.pi/3.0) + V0
        Vc = Vd * math.cos(theta + 2.0*math.pi/3.0) - Vq * math.sin(theta + 2.0*math.pi/3.0) + V0
        return Va, Vb, Vc

    def step(self, Va: float, Vb: float, Vc: float) -> tuple:
        """
        Ejecuta un paso del SRF-PLL a la tasa de micro-simulación (1 kHz).
        Returns: (Vd, Vq, theta, f_sys)
        """
        # Clarke: abc -> alpha, beta
        Valpha = (2.0/3.0) * (Va - 0.5*Vb - 0.5*Vc)
        Vbeta  = (2.0/3.0) * ((math.sqrt(3.0)/2.0)*(Vb - Vc))

        # Park: alpha, beta -> d, q usando theta actual
        cos_t = math.cos(self.theta)
        sin_t = math.sin(self.theta)
        Vd =  Valpha * cos_t + Vbeta * sin_t
        Vq = -Valpha * sin_t + Vbeta * cos_t

        # Lazo PI sobre v_q (error de fase -> 0)
        self._int_state += self.Ki * self.Ts * Vq
        self._int_state = max(-1000.0, min(1000.0, self._int_state))
        delta_omega = self.Kp * Vq + self._int_state

        # Actualización de frecuencia y ángulo (Euler hacia adelante)
        self.omega_est = self.omega_nom + delta_omega
        self.theta = (self.theta + self.omega_est * self.Ts) % (2.0 * math.pi)
        self.f_sys = self.omega_est / (2.0 * math.pi)

        return Vd, Vq, self.theta, self.f_sys

    def synthesize_vabc(self, V_mag: float, delta_rad: float = 0.0) -> tuple:
        """
        Sintetiza el vector trifásico balanceado instantáneo desde la magnitud fasorial.
        """
        Vpico = math.sqrt(2.0) * float(V_mag)
        angle = self.theta + delta_rad
        Va = Vpico * math.cos(angle)
        Vb = Vpico * math.cos(angle - 2.0*math.pi/3.0)
        Vc = Vpico * math.cos(angle + 2.0*math.pi/3.0)
        return Va, Vb, Vc

    def aplicar_transformadas(self, V_abc, Vqi=0.0):
        """
        Wrapper compatible con código previo.
        """
        Va, Vb, Vc = V_abc
        Valpha = (2.0/3.0) * (Va - 0.5 * Vb - 0.5 * Vc)
        Vbeta = (2.0/3.0) * (math.sqrt(3.0)/2.0 * Vb - math.sqrt(3.0)/2.0 * Vc)
        Vd, Vq, theta0, Fsys = self.step(Va, Vb, Vc)
        return Valpha, Vbeta, theta0, Vq, Vd, Fsys


class Transformadas(SRFPLL):
    """Clase para retrocompatibilidad con importaciones previas."""
    pass
