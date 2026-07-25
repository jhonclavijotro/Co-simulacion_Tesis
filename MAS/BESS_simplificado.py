from typing import Optional


class BateriaSimplificada:
    """Modelo energetico simplificado de bateria para co-simulacion MAS."""

    def __init__(
        self,
        V_nominal: float = 48.0,
        capacidad_Ah: float = 200.0,
        SoC_inicial: float = 0.5,
        N_serie: int = 10,
    ) -> None:
        self.V_pack: float = V_nominal * N_serie
        self.capacidad_Ah: float = capacidad_Ah
        self.E_wh: float = self.V_pack * capacidad_Ah
        self.SoC: float = max(0.0, min(1.0, SoC_inicial))
        self.P_ref: float = 0.0
        self.P_real: float = 0.0

    def step(self, dt: float, P_ref: float) -> None:
        self.P_ref = P_ref
        self.P_real = P_ref
        dSoC: float = -P_ref * dt / (self.E_wh * 3600.0)
        self.SoC = max(0.0, min(1.0, self.SoC + dSoC))
