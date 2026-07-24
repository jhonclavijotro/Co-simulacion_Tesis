class MPPTController:
    """Controlador de seguimiento del punto de maxima potencia (MPPT) por Perturbar y Observar (P&O)."""

    def __init__(self):
        """Inicializa el controlador MPPT con valores por defecto."""
        self.V_ref = 350.0
        self.V_old = 0.0
        self.P_old = 0.0
        self.paso = 1.0
        self.V_ref_min = 0.0
        self.V_ref_max = 400.0

    def step(self, V_array, I):
        """Ejecuta un paso del algoritmo P&O para actualizar la referencia de tension.

        Parametros:
            V_array: Tension medida del arreglo fotovoltaico [V]
            I: Corriente medida del arreglo fotovoltaico [A]

        Retorna:
            V_ref: Tension de referencia actualizada [V]
        """
        P = V_array * I
        dV = V_array - self.V_old
        dP = P - self.P_old
        self.V_old = V_array
        self.P_old = P
        if abs(dP) < 1e-6:
            return self.V_ref
        if dP > 0:
            if dV > 0:
                self.V_ref += self.paso
            else:
                self.V_ref -= self.paso
        else:
            if dV > 0:
                self.V_ref -= self.paso
            else:
                self.V_ref += self.paso
        self.V_ref = max(self.V_ref_min, min(self.V_ref, self.V_ref_max))
        return self.V_ref

    
