import numpy as np


class BuckBoost:
    """Convertidor DC-DC bidireccional para el acople bateria-bus DC.

    Controla la corriente de bateria para seguir la referencia de potencia
    (P_ref) proveniente del agente de consenso MAS.
    """

    def __init__(self):
        self.C_dc = 2000e-6
        self.L_bat = 500e-6
        self.Vdc = 400.0
        self.I_bat = 0.0

    def calcular_referencia_corriente(self, P_ref, V_bat):
        """Calcula I_bat_ref a partir de P_ref.

        Parametros:
            P_ref: Potencia de referencia (+ descarga, - carga) [W]
            V_bat: Voltaje de bateria [V]

        Retorna:
            I_bat_ref: Corriente de bateria de referencia [A]
        """
        if abs(V_bat) < 1.0:
            return 0.0
        return P_ref / V_bat

    def control_corriente(self, I_bat_ref, I_bat_actual, Kp=0.1):
        """Control PI proporcional para seguimiento de corriente.

        Parametros:
            I_bat_ref: Corriente de referencia [A]
            I_bat_actual: Corriente medida [A]
            Kp: Ganancia proporcional

        Retorna:
            duty: Ciclo de trabajo del convertidor [0-1]
        """
        error = I_bat_ref - I_bat_actual
        return np.clip(Kp * error, -0.9, 0.9)

    def actualizar_estado(self, duty, I_bat_ref, V_bat, Vdc, I_inv, dt):
        """Integra la dinamica del bus DC y la inductancia.

        Parametros:
            duty: Ciclo de trabajo
            I_bat_ref: Corriente de bateria de referencia [A]
            V_bat: Voltaje de bateria [V]
            Vdc: Tension del bus DC [V]
            I_inv: Corriente del inversor [A]
            dt: Paso de tiempo [s]

        Retorna:
            I_bat: Corriente de bateria [A]
            Vdc: Tension del bus DC actualizada [V]
        """
        dI_bat = (V_bat - Vdc * abs(duty)) / self.L_bat
        self.I_bat += dI_bat * dt

        I_dc = self.I_bat * abs(duty)
        dVdc = (I_dc - I_inv) / self.C_dc
        Vdc += dVdc * dt

        self.Vdc = max(300.0, min(Vdc, 500.0))
        return self.I_bat, self.Vdc
