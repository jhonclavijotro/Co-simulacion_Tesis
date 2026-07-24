import math

class Aerogenerador:
    """Modelo aerodinamico de un aerogenerador de eje horizontal."""

    def __init__(self, R, B):
        """Inicializa el aerogenerador con sus parametros fisicos.

        Parametros:
            R: Radio del rotor [m]
            B: Angulo de pitch [grados]
        """
        self.R = R
        self.B = B
        self.rho = 1.225

    def calcular_torque(self, Wr, Ws):
        """Calcula el torque mecanico en el eje del rotor.

        Parametros:
            Wr: Velocidad angular del rotor [rad/s]
            Ws: Velocidad del viento [m/s]

        Retorna:
            Torque mecanico [Nm]
        """
        c1 = 0.5176
        c2 = 116.0
        c3 = 0.4
        c4 = 5.0
        c5 = 21.0
        c6 = 0.0068
        ws = max(1e-6, min(Ws, 1e6))
        wr = max(1e-6, min(Wr, 1e6))
        lambda1 = (self.R * wr) / ws
        inv_lambda_i = 1.0 / (lambda1 + 0.08 * self.B) - 0.035 / (self.B**3 + 1.0)
        x = 1.0 / inv_lambda_i if inv_lambda_i != 0 else 1e6
        cp = c1 * (c2 / x - c3 * self.B - c4) * math.exp(-c5 / x) + c6 * lambda1
        area = math.pi * (self.R ** 2)
        pm = 0.5 * self.rho * area * (ws ** 3) * cp
        return -(pm / wr)

        