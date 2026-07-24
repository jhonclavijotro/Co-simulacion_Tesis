import numpy as np
from scipy import signal

class BoostConverter:
    def __init__(self):
        # Parámetros del convertidor
        self.C = 1000e-6      # Capacitancia del bus DC [F]
        self.L = 400e-6       # Inductancia [H]
        self.R = 0.1          # Resistencia parásita [Ω]
        self.Vdc = 300.0      # Tensión inicial del bus [V]
        self.Ipv = 0.0        # Corriente del panel [A]
        
        # Modelo de espacio de estados
        self.A = np.array([[0, -1/self.L],
                          [1/self.C, -1/(self.R*self.C)]])
        self.B = np.array([[1/self.L],
                          [0]])
        self.C_mat = np.eye(2)
        self.D = np.zeros((2,1))
        
    def calculate_duty_cycle(self, Vref, Vdc_actual):
        """Calcula el duty cycle para regulación de tensión"""
        error = Vref - Vdc_actual
        Kp = 0.01  # Ganancia proporcional
        duty = Kp * error
        return np.clip(duty, 0.1, 0.9)  # Limitar entre 10%-90%

    def update_state(self, duty_cycle, Ipv, Iinv, dt):
        """
        Actualiza el estado del convertidor con retroalimentación de Iinv
        Args:
            duty_cycle: Ciclo de trabajo [0-1]
            Ipv: Corriente del panel [A]
            Iinv: Corriente del inversor [A] (retroalimentación)
            dt: Paso de tiempo [s]
        Returns:
            Ipv_new, Vdc_new: Nuevos estados
        """
        # Modelo del condensador DC
        Iboost = Ipv / (1 - duty_cycle)  # Corriente de salida del boost
        dVdc = (Iboost - Iinv) / self.C  # Ecuación del condensador
        
        # Modelo del inductor
        dIpv = (self.Vdc * duty_cycle - Ipv * self.R) / self.L
        
        # Integración numérica (Euler)
        Ipv_new = self.Ipv + dIpv * dt
        Vdc_new = self.Vdc + dVdc * dt
        
        # Actualizar estados internos
        self.Ipv = Ipv_new
        self.Vdc = max(250, min(Vdc_new, 450))  # Límites de seguridad
        
        return Ipv_new, self.Vdc

    def get_state_space(self, duty_cycle):
        """Modelo linealizado para análisis"""
        B_modified = self.B * duty_cycle
        return signal.StateSpace(self.A, B_modified, self.C_mat, self.D)