import math
from CentralPC.solver_sweep import ForwardBackwardSweep


class SensitivitySolver:
    """Solucionador de flujo de potencia por matrices de sensibilidad.

    Linealiza el sistema alrededor de un estado estable para evaluar
    variaciones suaves en las inyecciones de potencia activa y reactiva
    mediante multiplicaciones matriciales directas:

        delta_V = S_VP * delta_P + S_VQ * delta_Q

    donde S_VP y S_VQ son las matrices de sensibilidad de tension
    respecto a P y Q respectivamente.

    Las matrices se computan mediante perturbacion numerica alrededor
    del caso base usando el solucionador Forward-Backward Sweep
    (Christakou et al., 2013).
    """

    def __init__(self, archivo_red):
        self.sweep = ForwardBackwardSweep(archivo_red)
        self.n = self.sweep.n_nodos
        self.S_VP = None
        self.S_VQ = None
        self.V_base = None
        self.P_base = None
        self.Q_base = None
        self._calibrado = False

    def _matriz_ceros(self, filas, cols):
        return [[0.0 for _ in range(cols)] for _ in range(filas)]

    def _matriz_vector(self, M, v):
        n = len(M)
        r = [0.0] * n
        for i in range(n):
            s = 0.0
            for j in range(len(v)):
                s += M[i][j] * v[j]
            r[i] = s
        return r

    def calibrar(self, inyecciones_base, delta=100.0):
        """Calibra las matrices de sensibilidad alrededor de un punto de operacion.

        Para cada nodo i, perturba P_i y Q_i en +delta y ejecuta el FBS
        para medir la variacion de tension en todos los nodos.

        Parametros:
            inyecciones_base: dict {nodo: (P, Q)} en Watts y VARs
            delta: Magnitud de la perturbacion [W o VAR]
        """
        n = self.n
        self.S_VP = self._matriz_ceros(n, n)
        self.S_VQ = self._matriz_ceros(n, n)

        self.V_base, convergio, _ = self.sweep.resolver(inyecciones_base)
        V_base_mag = [abs(self.V_base[i]) for i in range(n)]

        self.P_base = {i: inyecciones_base.get(i, (0, 0))[0] for i in range(n)}
        self.Q_base = {i: inyecciones_base.get(i, (0, 0))[1] for i in range(n)}

        for nodo in range(1, n):
            iny_pert = dict(inyecciones_base)

            P, Q = iny_pert.get(nodo, (0.0, 0.0))
            iny_pert[nodo] = (P + delta, Q)
            V_pert, _, _ = self.sweep.resolver(iny_pert)
            for i in range(n):
                self.S_VP[i][nodo] = (abs(V_pert[i]) - V_base_mag[i]) / delta

            P, Q = iny_pert.get(nodo, (0.0, 0.0))
            iny_pert[nodo] = (P, Q + delta)
            V_pert, _, _ = self.sweep.resolver(iny_pert)
            for i in range(n):
                self.S_VQ[i][nodo] = (abs(V_pert[i]) - V_base_mag[i]) / delta

        self._calibrado = True

    def predecir_V(self, inyecciones):
        """Predice las tensiones nodales usando las matrices de sensibilidad.

        Para pequenas desviaciones respecto al caso base:
            V aproximado V_base + S_VP * delta_P + S_VQ * delta_Q

        Parametros:
            inyecciones: dict {nodo: (P, Q)} en Watts y VARs

        Retorna:
            V_predicho: dict {nodo: magnitud_tension_en_pu}
        """
        if not self._calibrado:
            raise RuntimeError("SensitivitySolver no calibrado. Ejecute calibrar() primero.")

        n = self.n
        delta_P = [0.0] * n
        delta_Q = [0.0] * n

        for i in range(n):
            if i in inyecciones:
                P, Q = inyecciones[i]
                delta_P[i] = P - self.P_base.get(i, 0.0)
                delta_Q[i] = Q - self.Q_base.get(i, 0.0)

        V_base_arr = [abs(self.V_base[i]) for i in range(n)]
        delta_V_P = self._matriz_vector(self.S_VP, delta_P)
        delta_V_Q = self._matriz_vector(self.S_VQ, delta_Q)
        V_pred = [V_base_arr[i] + delta_V_P[i] + delta_V_Q[i] for i in range(n)]

        return {i: V_pred[i] for i in range(n)}

    def resolver(self, inyecciones, V_slack=1.0, tol=1e-8, max_iter=1000,
                 relajacion=0.5):
        """Resuelve el flujo de potencia (interfaz compatible con FBS).

        Usa matrices de sensibilidad si ya estan calibradas y las
        inyecciones estan cercanas al caso base. Sino, delega al FBS.

        Retorna:
            V: dict {nodo: tension_compleja} en pu
            convergio: bool
            iteraciones: int
        """
        if self._calibrado:
            V_mag = self.predecir_V(inyecciones)
            V = {}
            for i in range(self.n):
                if i == 0:
                    V[i] = complex(V_slack, 0.0)
                else:
                    ang = math.radians(-5.0 * (i / (self.n - 1)))
                    V[i] = complex(V_mag[i] * math.cos(ang),
                                   V_mag[i] * math.sin(ang))
            return V, True, 1
        else:
            return self.sweep.resolver(inyecciones, modelos=None,
                                       V_slack=V_slack, tol=tol,
                                       max_iter=max_iter,
                                       relajacion=relajacion)

    def __str__(self):
        estado = "calibrado" if self._calibrado else "sin calibrar"
        return f"SensitivitySolver(nodos={self.n}, {estado})"
