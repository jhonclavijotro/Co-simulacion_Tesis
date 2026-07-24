import math


class Bateria:
    """Modelo electroquimico de bateria de ion-litio (Shepherd simplificado).

    Implementa el modelo de circuito equivalente con V_oc(SoC) y R_int
    para simular la dinamica de la bateria en aplicaciones de red.
    """

    def __init__(self, V_nominal=48.0, capacidad_Ah=200.0, SoC_inicial=0.5,
                 R_int=0.01, N_serie=10, N_paralelo=1):
        self.V_nominal = V_nominal
        self.capacidad_Ah = capacidad_Ah
        self.SoC = max(0.0, min(1.0, SoC_inicial))
        self.R_int = R_int
        self.N_serie = N_serie
        self.N_paralelo = N_paralelo

        self.capacidad_total_Ah = capacidad_Ah * N_paralelo
        self.V_nominal_pack = V_nominal * N_serie
        self.V_oc = self.V_nominal_pack

    def calcular_V(self, I_bat):
        """Calcula el voltaje de la bateria segun SoC y corriente.

        V_bat = V_oc(SoC) - R_int * I_bat

        Parametros:
            I_bat: Corriente de la bateria (+ descarga, - carga) [A]

        Retorna:
            V_bat: Voltaje en bornes de la bateria [V]
        """
        V_oc_base = self._calcular_V_oc()
        self.V_oc = V_oc_base * self.N_serie
        V_bat = self.V_oc - self.R_int * self.N_serie * I_bat / self.N_paralelo
        return max(0.0, V_bat)

    def actualizar_SoC(self, I_bat, dt):
        """Actualiza el estado de carga mediante conteo de Coulomb.

        dSoC/dt = -I_bat / (capacidad_total_Ah * 3600)

        Parametros:
            I_bat: Corriente de la bateria (+ descarga, - carga) [A]
            dt: Paso de tiempo [s]
        """
        dSoC = -I_bat * dt / (self.capacidad_total_Ah * 3600.0)
        self.SoC = max(0.0, min(1.0, self.SoC + dSoC))

    def _calcular_V_oc(self):
        """Curva V_oc vs SoC parametrizada.

        Escala la curva tipica de una celda Li-ion (3.0-4.2 V/celda)
        al voltaje del modulo (V_nominal=48V). Luego calcular_V()
        multiplica por N_serie para obtener el voltaje del pack.

        Rango tipico del modulo 48V:
          SoC 0.0 -> ~40 V
          SoC 1.0 -> ~54 V
        """
        s = self.SoC
        V_cell = 3.0 + 1.2 * s + 0.5 * s ** 2 - 0.5 * s ** 3
        celdas_por_modulo = self.V_nominal / 3.6
        return V_cell * celdas_por_modulo

    def obtener_estado(self):
        return {
            "SoC": self.SoC,
            "V_oc": self.V_oc,
            "V_nominal_pack": self.V_nominal_pack,
            "capacidad_restante_Ah": self.SoC * self.capacidad_total_Ah
        }
