import math
from typing import Optional


class SolarSimplificado:
    """Modelo promediado de generacion solar para co-simulacion MAS.

    Perfil sintetico de irradiancia: campana gaussiana sobre T_total.
    Pico en t = T_total/2, ancho sigma = T_total/6.
    """

    def __init__(
        self,
        P_rated: float = 3000.0,
        T_total: float = 3600.0,
        sigma_frac: float = 1.0 / 6.0,
        V_base: float = 110.0,
    ) -> None:
        self.P_rated: float = P_rated
        self.T_total: float = T_total
        self.sigma: float = T_total * sigma_frac
        self.t: float = 0.0
        self.P_ref: float = 0.0
        self.P_real: float = 0.0
        self.SoC: float = 0.0
        self.V_base: float = V_base
        self.V_pcc_pu: float = 1.0

    def _perfil_potencia(self, t: float) -> float:
        mu = self.T_total / 2.0
        return self.P_rated * math.exp(-((t - mu) / self.sigma) ** 2)

    def step(self, dt: float, P_ref: float, V_pcc: Optional[float] = None) -> None:
        if V_pcc is not None:
            self.V_pcc_pu = V_pcc / self.V_base if self.V_base > 0 else 1.0
        else:
            self.V_pcc_pu = 1.0

        P_available = self._perfil_potencia(self.t)
        if self.V_pcc_pu < 0.50:
            P_available = 0.0
        elif self.V_pcc_pu < 0.88:
            factor = 0.88 * (self.V_pcc_pu - 0.50) / (0.88 - 0.50)
            P_available *= factor

        self.P_ref = P_available
        self.P_real = P_available
        self.SoC = P_available / self.P_rated if self.P_rated > 0 else 0.0
        self.t += dt
