import numpy as np
from scipy import signal

class BoostConverter:
    def __init__(self):
        # Parámetros del convertidor
        self.C = 1000e-6      # Capacitancia del bus DC [F]
        self.L = 400e-6       # Inductancia [H]
        self.R = 0.1          # Resistencia parásita [Ω]
        self.Vdc = 400.0      # Tensión inicial del bus [V] (debe ser > Vpv para Boost)
        self.Ipv = 7.6        # Corriente inicial del panel [A] (~Impp)
        self.last_P_cap = 0.0
        
        self.integral_error = 0.0
        
        # Modelo de espacio de estados
        self.A = np.array([[0, -1/self.L],
                          [1/self.C, -1/(self.R*self.C)]])
        self.B = np.array([[1/self.L],
                          [0]])
        self.C_mat = np.eye(2)
        self.D = np.zeros((2,1))
        
    def calculate_duty_cycle(self, Vref, Vpv_actual, Vdc, dt=0.001):
        """Calcula duty cycle del Boost usando feedforward + PI corrector.
        
        Feedforward: D_ff = 1 - Vref/Vdc (relacion algebraica exacta del Boost en CCM).
        PI corrector minimo para compensar perdidas no modeladas.
        """
        D_ff = 1.0 - Vref / Vdc if Vdc > 0 else 0.5
        error = Vpv_actual - Vref
        duty_unsat = D_ff + self.integral_error
        if 0.01 < duty_unsat < 0.95:
            self.integral_error += error * 0.02 * dt
        elif duty_unsat >= 0.95 and error < 0:
            self.integral_error += error * 0.02 * dt
        elif duty_unsat <= 0.01 and error > 0:
            self.integral_error += error * 0.02 * dt
        self.integral_error = max(-0.02, min(self.integral_error, 0.02))
        duty = D_ff + self.integral_error
        return np.clip(duty, 0.01, 0.95)

    def update_state(self, duty_cycle, Ipv, Vpv, Iinv, dt):
        """Actualiza el bus DC mediante balance energético exacto del capacitor C_dc:
          0.5 * C * d(Vdc^2)/dt = P_in - P_out
        donde P_in = Vpv * Ipv y P_out = Vdc * Iinv (corriente extraída por el inversor AC).
        """
        dt_s = max(1e-6, float(dt))
        v_old = float(self.Vdc)
        P_in = float(Vpv) * float(Ipv)
        P_out = v_old * float(Iinv)

        v_sq_new = v_old * v_old + (2.0 * dt_s / self.C) * (P_in - P_out)
        self.Vdc = float(np.sqrt(max(370.0 * 370.0, min(500.0 * 500.0, v_sq_new))))
        self.last_P_cap = 0.5 * self.C * (self.Vdc * self.Vdc - v_old * v_old) / dt_s

        return Ipv, self.Vdc

    def get_state_space(self, duty_cycle):
        """Modelo linealizado para análisis"""
        B_modified = self.B * duty_cycle
        return signal.StateSpace(self.A, B_modified, self.C_mat, self.D)