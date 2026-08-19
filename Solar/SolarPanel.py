import numpy as np
import math

class SolarPanel:
    """Modelo de panel fotovoltaico basado en el modelo de diodo simple."""

    def __init__(self):
        """Inicializa los parámetros eléctricos y físicos del panel."""
        # Coeficiente de temperatura de corriente de cortocircuito [A/K]
        self.Ki = 0.0032
        # Carga del electrón [C]
        self.q = 1.6e-19
        # Constante de Boltzmann [J/K]
        self.K = 1.38e-23
        # Factor de idealidad del diodo
        self.n = 1.3
        # Número de celdas en serie por panel
        self.Ns = 54
        # Energía de banda prohibida del silicio [eV]
        self.Eg0 = 1.1
        # Resistencia serie del panel [ohm]
        self.Rs = 0.221
        # Resistencia paralelo (shunt) del panel [ohm]
        self.Rsh = 415.405
        # Temperatura nominal de operación [K]
        self.Tn = 298
        # Voltaje de circuito abierto nominal [V]
        self.Voc = 32.9
        # Corriente de cortocircuito nominal [A]
        self.Isc = 8.21
        # Número de paneles conectados en serie en el arreglo
        self.num_panels = 14

    def calculate_output(self, poa, T):
        """Calcula la corriente, voltaje y potencia del panel para condiciones dadas.

        Parametros:
            poa: Irradiancia incidente en el plano del arreglo (Plane of Array) [W/m2]
            T: Temperatura de la celda [K]

        Retorna:
            V: Voltaje de una celda [V]
            I: Corriente del panel [A]
            V_array: Voltaje total del arreglo [V]
            P_array: Potencia total del arreglo [W]
        """
        # Corriente fotonica generada por la irradiancia
        Iph = self._photon_current(poa, T)
        # Corriente de saturacion inversa del diodo
        Irs = self._saturation_inverse_current(T)
        # Corriente de saturacion dependiente de la temperatura
        Io = self._saturation_current(T, Irs)
        # Corriente y voltaje del panel resolviendo la ecuacion caracteristica
        V, I = self._solve_panel_equation(Iph, Io, T)
        # Voltaje y potencia total del arreglo de paneles
        V_array = V * self.num_panels
        P_array = V_array * I
        return V, I, V_array, P_array

    def calculate_at_voltage(self, V_array, poa, T):
        Iph = self._photon_current(poa, T)
        Irs = self._saturation_inverse_current(T)
        Io = self._saturation_current(T, Irs)
        Vt = self.n * self.Ns * self.K * T / self.q
        V_panel = V_array / self.num_panels
        return self._current_at_voltage(V_panel, Iph, Io, Vt)

    def _photon_current(self, poa, T):
        """Calcula la corriente fotonica generada por la irradiancia incidente.

        Parametros:
            poa: Irradiancia en el plano del arreglo [W/m2]
            T: Temperatura de la celda [K]

        Retorna:
            Iph: Corriente fotonica [A]
        """
        return (poa / 1000.0) * (self.Isc - (self.Ki * (T - self.Tn)))

    def _saturation_inverse_current(self, T):
        """Calcula la corriente de saturacion inversa del diodo.

        Parametros:
            T: Temperatura de la celda [K]

        Retorna:
            Irs: Corriente de saturacion inversa [A]
        """
        exponent = self.q * self.Voc / (self.n * self.Ns * self.K * T)
        p = math.exp(exponent) - 1.0
        return self.Isc / p

    def _saturation_current(self, T, Irs):
        """Calcula la corriente de saturacion del diodo ajustada por temperatura.

        Parametros:
            T: Temperatura de la celda [K]
            Irs: Corriente de saturacion inversa [A]

        Retorna:
            Io: Corriente de saturacion [A]
        """
        exponent = ((1.0 / self.Tn) - (1.0 / T)) * ((self.Eg0 * self.q) / (self.n * self.K))
        return Irs * ((T / self.Tn) ** 3) * math.exp(exponent)

    def _current_at_voltage(self, V, Iph, Io, Vt):
        """Calcula la corriente del panel a un voltaje dado usando iteracion de punto fijo.

        Resuelve la ecuacion del modelo de diodo simple:
            I = Iph - Io*(exp((V + I*Rs)/Vt) - 1) - (V + I*Rs)/Rsh

        Parametros:
            V: Voltaje del panel [V]
            Iph: Corriente fotonica [A]
            Io: Corriente de saturacion [A]
            Vt: Voltaje termico [V]

        Retorna:
            I: Corriente del panel [A]
        """
        I = Iph
        for _ in range(10):
            Vd = V + I * self.Rs
            arg = Vd / Vt
            if arg > 50:
                I_diode = Io * (math.exp(50) - 1.0) + Io * math.exp(50) * (arg - 50)
            else:
                I_diode = Io * (math.exp(arg) - 1.0)
            I_shunt = Vd / self.Rsh
            I_new = Iph - I_diode - I_shunt
            if abs(I_new - I) < 1e-6:
                break
            I = I_new
        return I

    def _solve_panel_equation(self, Iph, Io, T):
        """Encuentra el punto de operacion del panel (V cerca del MPP).

        Usa barrido desde Voc hacia abajo para encontrar el punto
        de maxima potencia en la curva I-V.

        Retorna:
            V: Voltaje de operacion del panel [V]
            I: Corriente de operacion del panel [A]

    def calculate_at_voltage(self, V_array, poa, T):
        Iph = self._photon_current(poa, T)
        Irs = self._saturation_inverse_current(T)
        Io = self._saturation_current(T, Irs)
        """
        Vt = self.n * self.Ns * self.K * T / self.q

        def current(V):
            return self._current_at_voltage(V, Iph, Io, Vt)

        V_oc = self.Voc
        best_V, best_P = 0, 0
        for frac in [0.85, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55]:
            V = V_oc * frac
            I = current(V)
            if I <= 0:
                continue
            P = V * I
            if P > best_P:
                best_V, best_P = V, P

        V, I = best_V, current(best_V)
        return V, I