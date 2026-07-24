class BateriaSimplificada:
    """Modelo energetico simplificado de bateria para co-simulacion MAS.

    P_ref > 0: descarga (potencia fluye hacia la red)
    P_ref < 0: carga (potencia fluye desde la red)

    dSoC/dt = -P_ref / (V_pack * capacidad_Ah * 3600)
    """

    def __init__(self, V_nominal=48.0, capacidad_Ah=200.0, SoC_inicial=0.5,
                 N_serie=10):
        self.V_pack = V_nominal * N_serie
        self.capacidad_Ah = capacidad_Ah
        self.E_wh = self.V_pack * capacidad_Ah
        self.SoC = max(0.0, min(1.0, SoC_inicial))
        self.P_ref = 0.0
        self.P_real = 0.0

    def step(self, dt, P_ref):
        self.P_ref = P_ref
        self.P_real = P_ref
        dSoC = -P_ref * dt / (self.E_wh * 3600.0)
        self.SoC = max(0.0, min(1.0, self.SoC + dSoC))
