import csv


class PerfilDemanda:
    """Perfil de demanda de potencia activa (P) y reactiva (Q).

    Soporta dos modos:
      1. Perfil programatico (funcion de tiempo)
      2. Perfil desde archivo CSV

    En Modo CSV, el archivo debe tener columnas: tiempo, P, Q
    Los valores entre muestras se obtienen por interpolacion lineal.
    """

    def __init__(self, archivo_csv=None, P_nominal=10000.0, Q_nominal=0.0):
        self.P_nominal = P_nominal
        self.Q_nominal = Q_nominal
        self._datos = None

        if archivo_csv:
            self._cargar_csv(archivo_csv)

    def _cargar_csv(self, archivo):
        """Carga perfil desde CSV con columnas: tiempo, P, Q."""
        self._datos = {"tiempo": [], "P": [], "Q": []}
        with open(archivo, "r") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                try:
                    self._datos["tiempo"].append(float(row[0]))
                    self._datos["P"].append(float(row[1]))
                    self._datos["Q"].append(float(row[2]))
                except (ValueError, IndexError):
                    continue

    def obtener_en_tiempo(self, t):
        """Retorna (P, Q) para el instante t.

        En modo CSV usa interpolacion lineal entre muestras.
        En modo programatico usa funciones por defecto.
        """
        if self._datos:
            return self._interpolar(t)
        return self._perfil_programatico(t)

    def _interpolar(self, t):
        """Interpolacion lineal entre puntos del CSV."""
        tiempos = self._datos["tiempo"]
        if not tiempos:
            return self.P_nominal, self.Q_nominal
        if t <= tiempos[0]:
            return self._datos["P"][0], self._datos["Q"][0]
        if t >= tiempos[-1]:
            return self._datos["P"][-1], self._datos["Q"][-1]
        for i in range(len(tiempos) - 1):
            if tiempos[i] <= t < tiempos[i + 1]:
                fraccion = (t - tiempos[i]) / (tiempos[i + 1] - tiempos[i])
                P = self._datos["P"][i] + fraccion * (self._datos["P"][i + 1] - self._datos["P"][i])
                Q = self._datos["Q"][i] + fraccion * (self._datos["Q"][i + 1] - self._datos["Q"][i])
                return P, Q
        return self._datos["P"][-1], self._datos["Q"][-1]

    def _perfil_programatico(self, t):
        """Perfil por defecto con variacion escalonada."""
        if t < 2:
            return self.P_nominal * 0.5, self.Q_nominal
        elif t < 5:
            return self.P_nominal * 0.8, self.Q_nominal
        elif t < 8:
            return self.P_nominal * 1.0, self.Q_nominal
        elif t < 12:
            return self.P_nominal * 0.6, self.Q_nominal
        else:
            return self.P_nominal * 0.4, self.Q_nominal
