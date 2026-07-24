import csv
import math
import cmath


class ForwardBackwardSweep:
    """Solucionador de flujo de potencia para redes radiales de distribucion.

    Implementa el algoritmo Forward-Backward Sweep (Barrido Iterativo)
    utilizando el metodo descrito en Chang et al. (2007) y Bompard et al.
    (2000). Resuelve la topologia radial calculando tensiones nodales
    a partir de las inyecciones de potencia activa y reactiva.

    La red se define mediante un archivo CSV con columnas:
      from_node, to_node, R_ohm, X_ohm, length_m
    donde el nodo 0 es la subestacion (slack bus).
    """

    def __init__(self, archivo_red):
        self.ramas = []
        self.nodos = set()
        self._cargar_red(archivo_red)
        self._construir_topologia()
        self._ordenar_por_capas()

    def _cargar_red(self, archivo):
        """Carga la topologia de la red desde un archivo CSV."""
        self.ramas = []
        self.nodos = set()
        with open(archivo, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rama = {
                    "from": int(row["from_node"]),
                    "to": int(row["to_node"]),
                    "R": float(row["R_ohm"]),
                    "X": float(row["X_ohm"]),
                    "Z": complex(float(row["R_ohm"]), float(row["X_ohm"])),
                    "length": float(row.get("length_m", 0)),
                }
                self.ramas.append(rama)
                self.nodos.add(rama["from"])
                self.nodos.add(rama["to"])
        self.n_nodos = max(self.nodos) + 1
        self.n_ramas = len(self.ramas)

    def _construir_topologia(self):
        """Construye la matriz de incidencia y las relaciones padre-hijo."""
        hijos = {i: [] for i in range(self.n_nodos)}
        padres = {}
        impedancia_rama = {}

        for rama in self.ramas:
            f = rama["from"]
            t = rama["to"]
            hijos[f].append(t)
            padres[t] = f
            impedancia_rama[(f, t)] = rama["Z"]

        self.hijos = hijos
        self.padres = padres
        self.impedancia_rama = impedancia_rama

    def _ordenar_por_capas(self):
        """Determina el orden de recorrido por capas desde la raiz.

        La capa 0 es el nodo slack (subestacion).
        Las capas sucesivas son los nodos a cada distancia de la raiz.
        """
        capas = [{0}]
        visitados = {0}
        while True:
            siguiente_capa = set()
            for nodo in capas[-1]:
                for hijo in self.hijos[nodo]:
                    if hijo not in visitados:
                        siguiente_capa.add(hijo)
                        visitados.add(hijo)
            if not siguiente_capa:
                break
            capas.append(siguiente_capa)

        self.capas = capas
        self.orden_inverso = []
        for capa in reversed(capas):
            self.orden_inverso.extend(sorted(capa))

    def resolver(self, inyecciones, V_slack=1.0, tol=1e-8, max_iter=1000, relajacion=0.5):
        """Resuelve el flujo de potencia para una carga dada.

        Parametros:
            inyecciones: dict {nodo: (P, Q)} en Watts y VARs
            V_slack: Tension del nodo slack en por unidad
            tol: Tolerancia de convergencia
            max_iter: Maximo de iteraciones

        Retorna:
            V: dict {nodo: tension_compleja} en por unidad
            convergio: bool
            iteraciones: int
        """
        V_base = 110.0
        S_base = 10000.0
        Z_base = (V_base ** 2) / S_base

        V = {i: complex(1.0, 0.0) for i in range(self.n_nodos)}
        V[0] = complex(V_slack, 0.0)

        S_pu = {}
        for nodo in range(1, self.n_nodos):
            if nodo in inyecciones:
                P, Q = inyecciones[nodo]
                S_pu[nodo] = complex(P, Q) / S_base
            else:
                S_pu[nodo] = complex(0, 0)

        Z_pu = {}
        for rama in self.ramas:
            f, t = rama["from"], rama["to"]
            Z_pu[(f, t)] = rama["Z"] / Z_base

        for it in range(max_iter):
            V_old = V.copy()

            I_ramas = {}
            I_nodo = {i: complex(0, 0) for i in range(self.n_nodos)}

            for nodo in self.orden_inverso:
                if nodo == 0:
                    continue
                S = S_pu.get(nodo, complex(0, 0))
                if abs(V[nodo]) > 1e-10:
                    I_nodo[nodo] = (S / V[nodo]).conjugate()
                for hijo in self.hijos[nodo]:
                    if (nodo, hijo) in I_ramas:
                        I_nodo[nodo] += I_ramas[(nodo, hijo)]

                padre = self.padres.get(nodo)
                if padre is not None:
                    I_ramas[(padre, nodo)] = I_nodo[nodo]

            for capa in self.capas[1:]:
                for nodo in sorted(capa):
                    padre = self.padres.get(nodo)
                    if padre is not None:
                        Z = Z_pu.get((padre, nodo), complex(0, 0))
                        I = I_ramas.get((padre, nodo), complex(0, 0))
                        V_new = V[padre] - Z * I
                        V[nodo] = (1 - relajacion) * V_old[nodo] + relajacion * V_new

            delta_max = 0.0
            for nodo in range(1, self.n_nodos):
                delta = abs(V[nodo] - V_old[nodo])
                if delta > delta_max:
                    delta_max = delta
            if delta_max < tol:
                return V, True, it + 1

        return V, False, max_iter

    def tensiones_a_dict(self, V_complejo):
        """Convierte tensiones complejas a diccionario con modulo y angulo."""
        return {
            nodo: {
                "magnitud": abs(V_complejo[nodo]),
                "angulo_grados": math.degrees(cmath.phase(V_complejo[nodo])),
                "real": V_complejo[nodo].real,
                "imag": V_complejo[nodo].imag,
            }
            for nodo in range(self.n_nodos)
        }

    def __str__(self):
        return (f"ForwardBackwardSweep("
                f"nodos={self.n_nodos}, ramas={self.n_ramas}, "
                f"capas={len(self.capas)})")
