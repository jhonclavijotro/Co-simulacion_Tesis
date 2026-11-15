import csv


class PerfilDemanda:
    """Perfil de demanda de potencia activa (P) y reactiva (Q).

    Soporta dos modos:
      1. Perfil programatico (funcion de tiempo)
      2. Perfil desde archivo CSV

    En modo CSV las columnas se resuelven **por nombre de cabecera**, no por
    posición. Formatos aceptados:

      - consolidado rev.5: `timestamp,tiempo_s,...,P_kW,Q_kvar,fp`
      - legacy por nodo:   `timestamp,tiempo_s,P_kW,Q_kvar,S_kva,fp`
      - mínimo:            `tiempo_s,P,Q`
      - sin cabecera:      `tiempo,P,Q` (compatibilidad posicional)

    Los valores entre muestras se obtienen por interpolacion lineal.
    """

    # Nombres aceptados por columna (en minúsculas, sin prefijo de nodo).
    _COL_TIEMPO = ("tiempo_s", "tiempo", "time", "time_sec", "t")
    _COL_P = ("p_kw", "p", "p_demand")
    _COL_Q = ("q_kvar", "q", "q_demand")

    def __init__(self, archivo_csv=None, P_nominal=10000.0, Q_nominal=0.0):
        self.P_nominal = P_nominal
        self.Q_nominal = Q_nominal
        self._datos = None

        if archivo_csv:
            self._cargar_csv(archivo_csv)

    @classmethod
    def _buscar_columna(cls, cabecera, candidatos):
        normalizada = [c.strip().lower() for c in cabecera]
        for nombre in candidatos:
            if nombre in normalizada:
                return normalizada.index(nombre)
        return None

    def _indices(self, cabecera):
        """Devuelve (i_tiempo, i_P, i_Q) o None si no hay cabecera reconocible."""
        i_t = self._buscar_columna(cabecera, self._COL_TIEMPO)
        i_p = self._buscar_columna(cabecera, self._COL_P)
        if i_t is None or i_p is None:
            return None
        i_q = self._buscar_columna(cabecera, self._COL_Q)
        return i_t, i_p, i_q

    def _cargar_csv(self, archivo):
        """Carga el perfil resolviendo las columnas por cabecera."""
        self._datos = {"tiempo": [], "P": [], "Q": []}
        with open(archivo, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            try:
                cabecera = [h.strip() for h in next(reader)]
            except StopIteration:
                return

            indices = self._indices(cabecera)
            if indices is None:
                if any(h and not h.replace(".", "").replace("-", "").isdigit()
                       for h in cabecera):
                    # Hay texto en la cabecera pero ningún nombre reconocible:
                    # no se adivina por posición (evita leer 'timestamp' como P).
                    raise ValueError(
                        f"Cabecera no reconocible en {archivo}: {cabecera}. "
                        "Se esperaba 'tiempo_s' y 'P_kW'/'P'.")
                # Cabecera numérica => es la primera fila de datos (formato sin cabecera).
                indices = (0, 1, 2)
                filas = [cabecera]
            else:
                filas = reader

            i_t, i_p, i_q = indices
            for row in filas:
                if len(row) <= max(i_t, i_p):
                    continue
                try:
                    tiempo = float(row[i_t])
                    p = float(row[i_p])
                    q = float(row[i_q]) if i_q is not None and len(row) > i_q else 0.0
                except (ValueError, IndexError):
                    continue
                self._datos["tiempo"].append(tiempo)
                self._datos["P"].append(p)
                self._datos["Q"].append(q)

    def obtener_en_tiempo(self, t):
        """Retorna (P, Q) para el instante t.

        En modo CSV usa interpolacion lineal entre muestras.
        En modo programatico usa funciones por defecto.
        """
        if self._datos and self._datos["tiempo"]:
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
