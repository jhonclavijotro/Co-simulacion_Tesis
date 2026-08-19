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
        """Actualiza el bus DC usando corriente del panel como fuente.
        No modela la dinámica del inductor (L/R << dt de control).
        Usa solo la dinámica del capacitor del bus DC:
          C * dVdc/dt = (1-D)*Ipv - Iinv
        Args:
            duty_cycle: Ciclo de trabajo [0-1]
            Ipv: Corriente del panel (limitada por curva I-V) [A]
            Vpv: Tensión del arreglo fotovoltaico [V] (no usada directamente)
            Iinv: Corriente del inversor (carga del bus DC) [A]
            dt: Paso de tiempo [s]
        Returns:
            Ipv, Vdc_new: Ipv sin cambios (el panel la impone), Vdc actualizado
        """
        Iboost = Ipv * (1 - duty_cycle)
        dVdc = (Iboost - Iinv) / self.C
        
        Vdc_new = self.Vdc + dVdc * dt
        self.Vdc = max(370.0, min(Vdc_new, 500.0))
        
        return Ipv, self.Vdc

    def get_state_space(self, duty_cycle):
        """Modelo linealizado para análisis"""
        B_modified = self.B * duty_cycle
        return signal.StateSpace(self.A, B_modified, self.C_mat, self.D)