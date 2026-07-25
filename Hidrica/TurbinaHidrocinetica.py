import numpy as np


class TurbinaHidrocinetica:
    """Modelo hidrodinamico de una turbina hidrocinetica de eje horizontal.

    Adaptado del modelo aerodinamico del aerogenerador (Aerogenerador).
    La unica diferencia estructural es la densidad del fluido:
      - Aire:  rho = 1.225 kg/m3
      - Agua:  rho = 1000.0 kg/m3  (~816 veces mas denso)

    Por tanto, para una misma potencia, el rotor hidrocinetico puede ser
    significativamente menor que un aerogenerador.
    """

    def __init__(self, R, B):
        """Inicializa la turbina hidrocinetica con sus parametros fisicos.

        Parametros:
            R: Radio del rotor [m]
            B: Angulo de pitch [grados]
        """
        self.R = R
        self.B = B
        self.rho = 1000.0

    def calcular_torque(self, Wr, Vc):
        """Calcula el torque mecanico en el eje del rotor.

        Parametros:
            Wr: Velocidad angular del rotor [rad/s]
            Vc: Velocidad de la corriente de agua [m/s]

        Retorna:
            Torque mecanico [Nm]
        """
        c1 = 0.5176
        c2 = 116.0
        c3 = 0.4
        c4 = 5.0
        c5 = 21.0
        c6 = 0.0068
        vc = max(1e-6, min(Vc, 1e6))
        wr = max(1e-6, min(Wr, 1e6))
        lambda1 = (self.R * wr) / vc
        inv_lambda_i = 1.0 / (lambda1 + 0.08 * self.B) - 0.035 / (self.B**3 + 1.0)
        x = 1.0 / inv_lambda_i if inv_lambda_i != 0 else 1e6
        cp = c1 * (c2 / x - c3 * self.B - c4) * np.exp(-c5 / x) + c6 * lambda1
        area = np.pi * (self.R ** 2)
        pm = 0.5 * self.rho * area * (vc ** 3) * cp
        return -(pm / wr)
