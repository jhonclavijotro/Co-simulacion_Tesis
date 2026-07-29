from typing import Optional


class BateriaSimplificada:
    """Modelo energetico simplificado de bateria para co-simulacion MAS.

    Incluye limitacion LVRT basada en V_pcc:
      - V_pcc >= 0.88 pu: operacion normal
      - 0.50 <= V_pcc < 0.88 pu: derating lineal
      - V_pcc < 0.50 pu: potencia cero (trip)
    """

    def __init__(
        self,
        V_nominal: float = 48.0,
        capacidad_Ah: float = 200.0,
        SoC_inicial: float = 0.5,
        N_serie: int = 10,
        V_base: float = 110.0,
        eta_charge: float = 0.92,
        eta_discharge: float = 0.95,
    ) -> None:
        self.V_pack: float = V_nominal * N_serie
        self.capacidad_Ah: float = capacidad_Ah
        self.E_wh: float = self.V_pack * capacidad_Ah
        self.SoC: float = max(0.0, min(1.0, SoC_inicial))
        self.P_ref: float = 0.0
        self.P_real: float = 0.0
        self.V_base: float = V_base
        self.V_pcc_pu: float = 1.0
        self.lvrt_scaling: float = 1.0
        self.eta_charge: float = eta_charge
        self.eta_discharge: float = eta_discharge

    def _lvrt_factor(self, V_pcc_pu: float) -> float:
        if V_pcc_pu >= 0.88:
            return 1.0
        elif V_pcc_pu >= 0.50:
            return 0.88 * (V_pcc_pu - 0.50) / (0.88 - 0.50)
        else:
            return 0.0

    def step(self, dt: float, P_ref: float, V_pcc: Optional[float] = None) -> None:
        self.P_ref = P_ref

        if V_pcc is not None:
            self.V_pcc_pu = V_pcc / self.V_base if self.V_base > 0 else 1.0
        else:
            self.V_pcc_pu = 1.0

        self.lvrt_scaling = self._lvrt_factor(self.V_pcc_pu)
        P_ref_lvrt = P_ref * self.lvrt_scaling

        self.P_real = P_ref_lvrt

        if P_ref_lvrt >= 0:
            P_chem = P_ref_lvrt / self.eta_discharge
        else:
            P_chem = P_ref_lvrt * self.eta_charge

        dSoC: float = -P_chem * dt / (self.E_wh * 3600.0)
        self.SoC = max(0.0, min(1.0, self.SoC + dSoC))
