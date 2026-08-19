import math

class GridConnectedInverter:
    """Inversor Trifásico Conectado a Red con Regulación de Bus DC y Agregación de Múltiples Inversores en Paralelo.
    
    Permite modelar tanto un inversor unitario de Baja Tensión (BT) como una planta agregada de N_inv inversores en paralelo
    conectados a la red a través de un transformador elevador (BT -> MT).
    
    Impedancia equivalente de salida:
        Z_eq = (R_out_unit / N_inv + R_trafo) + j * (X_out_unit / N_inv + X_trafo)
    Capacidad aparente agregada:
        S_max_total = N_inv * S_inv_nom
    """
    def __init__(self, Vdcref=400.0, N_inv=1, S_inv_nom=100000.0,
                 R_out_unit=0.02, X_out_unit=0.10, R_trafo=0.01, X_trafo=0.05):
        self.Vdcref = Vdcref
        self.N_inv = max(1, int(N_inv))
        self.S_inv_nom = float(S_inv_nom)
        self.R_out_unit = float(R_out_unit)
        self.X_out_unit = float(X_out_unit)
        self.R_trafo = float(R_trafo)
        self.X_trafo = float(X_trafo)
        
        self.Idi_ref = 0.0
        self.Iqi_ref = 0.0

    @property
    def S_max_total(self):
        """Potencia aparente nominal agregada de la planta [VA]."""
        return self.N_inv * self.S_inv_nom

    @property
    def R_eq(self):
        """Resistencia equivalente vista desde el punto de acoplamiento [Ohm]."""
        return (self.R_out_unit / self.N_inv) + self.R_trafo

    @property
    def X_eq(self):
        """Reactancia equivalente vista desde el punto de acoplamiento [Ohm]."""
        return (self.X_out_unit / self.N_inv) + self.X_trafo

    @property
    def Z_eq(self):
        """Impedancia compleja equivalente vista desde el punto de acoplamiento [Ohm]."""
        return complex(self.R_eq, self.X_eq)

    def step(self, V_dc, Vdi, Vqi, theta0, I_dc_in, dt, Q_ref=0.0, **kwargs):
        # Control de corriente por inversor unitario
        error_vdc = self.Vdcref - V_dc
        self.Idi_ref = max(0.0, error_vdc * 2.0 + I_dc_in)
        self.Iqi_ref = -Q_ref / (1.5 * max(Vdi, 1.0) * self.N_inv) if Vdi > 0 else 0.0

        # Inyección total agregada escalada por N_inv inversores en paralelo
        Idi_total = self.Idi_ref * self.N_inv
        Iqi_total = self.Iqi_ref * self.N_inv

        Pw = 1.5 * max(Vdi, 1.0) * Idi_total
        Pq = -1.5 * max(Vdi, 1.0) * Iqi_total
        Idi = Idi_total
        Iqi = Iqi_total
        Vdt = Vdi
        Idiref = Idi_total

        return Pw, Pq, Idi, Iqi, Vdt, Idiref

