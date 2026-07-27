import csv
import math
import cmath

from CentralPC.transformador import TransformadorTrifasico, CONEXIONES

V_BASE_DEFAULT = 110.0
S_BASE = 10000.0


class ForwardBackwardSweep:
    """Solucionador de flujo de potencia para redes radiales de distribucion.

    Implementa el algoritmo Forward-Backward Sweep (Barrido Iterativo)
    utilizando el metodo descrito en Chang et al. (2007) y Bompard et al.
    (2000). Resuelve la topologia radial calculando tensiones nodales
    a partir de las inyecciones de potencia activa y reactiva.

    La red se define mediante un archivo CSV con columnas:
      from_node, to_node, R_ohm, X_ohm, length_m, [V_base]
    donde el nodo 0 es la subestacion (slack bus, V_base por defecto 110 V).

    Para incluir transformadores trifasicos, agregar columnas:
      tipo, V_pri, V_sec, S, Z_pct, X_R, conexion

    Ejemplo de rama transformador:
      from_node,to_node,R_ohm,X_ohm,V_base,tipo,V_pri,V_sec,S,Z_pct,X_R,conexion
      0,3,0.5,2.5,13800,transformador,13800,110,100000,5.75,5,Dyn11
    """

    def __init__(self, archivo_red):
        self.ramas = []
        self.nodos = set()
        self.v_base_nodo = {}
        self._cargar_red(archivo_red)
        self._construir_topologia()
        self._ordenar_por_capas()

    def _cargar_red(self, archivo):
        self.ramas = []
        self.nodos = set()
        self.v_base_nodo = {}
        with open(archivo, "r") as f:
            lines = [l for l in f if not l.startswith("#") and l.strip()]
            reader = csv.DictReader(lines)
            for row in reader:
                f_n = int(row["from_node"])
                t_n = int(row["to_node"])
                R = float(row["R_ohm"])
                X_val = float(row["X_ohm"])
                Z = complex(R, X_val)

                rama = {
                    "from": f_n, "to": t_n,
                    "R": R, "X": X_val, "Z": Z,
                    "length": float(row["length_m"]) if row.get("length_m") else 0,
                    "tipo": row.get("tipo", "linea").strip().lower(),
                }

                v_base = float(row["V_base"]) if "V_base" in row and row["V_base"].strip() else V_BASE_DEFAULT
                if f_n not in self.v_base_nodo:
                    self.v_base_nodo[f_n] = v_base
                if t_n not in self.v_base_nodo:
                    self.v_base_nodo[t_n] = v_base

                if rama["tipo"] == "transformador":
                    V_pri = float(row["V_pri"])
                    V_sec = float(row["V_sec"])
                    S_tr = float(row["S"])
                    Z_pct = float(row.get("Z_pct", 5.75))
                    X_R = float(row.get("X_R", 5))
                    conexion = row.get("conexion", "Dyn11")
                    tr = TransformadorTrifasico(S_tr, V_pri, V_sec, Z_pct, X_R, conexion)
                    rama["transformador"] = tr
                    self.v_base_nodo[t_n] = V_sec

                self.ramas.append(rama)
                self.nodos.add(f_n)
                self.nodos.add(t_n)
        self.n_nodos = max(self.nodos) + 1
        self.n_ramas = len(self.ramas)

        for n in sorted(self.nodos):
            if n not in self.v_base_nodo:
                self.v_base_nodo[n] = V_BASE_DEFAULT

    def _construir_topologia(self):
        hijos = {i: [] for i in range(self.n_nodos)}
        padres = {}
        impedancia_rama = {}
        transformador_rama = {}

        for rama in self.ramas:
            f = rama["from"]
            t = rama["to"]
            hijos[f].append(t)
            padres[t] = f
            impedancia_rama[(f, t)] = rama["Z"]
            if rama["tipo"] == "transformador":
                transformador_rama[(f, t)] = rama["transformador"]

        self.hijos = hijos
        self.padres = padres
        self.impedancia_rama = impedancia_rama
        self.transformador_rama = transformador_rama

    def _ordenar_por_capas(self):
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

    def _z_pu(self, f, t, Z_physical):
        vb = self.v_base_nodo.get(f, V_BASE_DEFAULT)
        return Z_physical / (vb ** 2 / S_BASE)

    def _corriente_carga(self, S_pu, modelo, V_pu):
        """Calcula corriente de carga segun modelo: PQ, Z, o I.

        S_pu: potencia compleja en pu
        modelo: "PQ" (default), "Z" (impedancia constante), "I" (corriente constante)
        V_pu: tension compleja en pu
        """
        v_abs = abs(V_pu)
        if v_abs < 1e-10:
            return complex(0, 0)
        if modelo == "Z":
            return V_pu * S_pu.conjugate()
        elif modelo == "I":
            return abs(S_pu) * V_pu / v_abs
        else:
            return (S_pu / V_pu).conjugate()

    def resolver(self, inyecciones, modelos=None, V_slack=1.0, tol=1e-8, max_iter=1000, relajacion=0.5):
        """Resuelve el flujo de potencia para una carga dada.

        Parametros:
            inyecciones: dict {nodo: (P, Q)} en Watts y VARs
            modelos: dict {nodo: "PQ"|"Z"|"I"} — modelo de carga (default "PQ")
            V_slack: Tension del nodo slack en por unidad (en su propia V_base)
            tol: Tolerancia de convergencia
            max_iter: Maximo de iteraciones

        Retorna:
            V: dict {nodo: tension_compleja} en por unidad (cada nodo en su V_base)
            convergio: bool
            iteraciones: int
        """
        V = {i: complex(1.0, 0.0) for i in range(self.n_nodos)}
        V[0] = complex(V_slack, 0.0)

        S_pu = {}
        for nodo in range(1, self.n_nodos):
            if nodo in inyecciones:
                P, Q = inyecciones[nodo]
                S_pu[nodo] = complex(P, Q) / S_BASE
            else:
                S_pu[nodo] = complex(0, 0)

        Z_pu = {}
        for rama in self.ramas:
            f, t = rama["from"], rama["to"]
            Z_pu[(f, t)] = self._z_pu(f, t, rama["Z"])

        for it in range(max_iter):
            V_old = V.copy()

            I_ramas = {}
            I_nodo = {i: complex(0, 0) for i in range(self.n_nodos)}

            for nodo in self.orden_inverso:
                if nodo == 0:
                    continue
                S = S_pu.get(nodo, complex(0, 0))
                md = modelos.get(nodo, "PQ") if modelos else "PQ"
                I_nodo[nodo] = self._corriente_carga(S, md, V[nodo])
                for hijo in self.hijos[nodo]:
                    if (nodo, hijo) in I_ramas:
                        I_nodo[nodo] += I_ramas[(nodo, hijo)]

                padre = self.padres.get(nodo)
                if padre is not None:
                    if (padre, nodo) in self.transformador_rama:
                        tr = self.transformador_rama[(padre, nodo)]
                        angle_rad = math.radians(-tr.angle)
                        shift = complex(math.cos(angle_rad), math.sin(angle_rad))
                        I_ramas[(padre, nodo)] = I_nodo[nodo] * shift
                    else:
                        I_ramas[(padre, nodo)] = I_nodo[nodo]

            for capa in self.capas[1:]:
                for nodo in sorted(capa):
                    padre = self.padres.get(nodo)
                    if padre is not None:
                        if (padre, nodo) in self.transformador_rama:
                            tr = self.transformador_rama[(padre, nodo)]
                            angle_rad = math.radians(tr.angle)
                            shift = complex(math.cos(angle_rad), math.sin(angle_rad))
                            V_pri_V = V[padre] * self.v_base_nodo[padre]
                            I_pu = I_ramas.get((padre, nodo), complex(0, 0))
                            I_A = I_pu * S_BASE / (self.v_base_nodo[padre] * math.sqrt(3))
                            V_sec_V = (V_pri_V * shift - tr.Z * I_A) / tr.N
                            V_new = V_sec_V / self.v_base_nodo[nodo]
                        else:
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
        res = {}
        for nodo in range(self.n_nodos):
            v_pu = V_complejo[nodo]
            vb = self.v_base_nodo.get(nodo, V_BASE_DEFAULT)
            res[nodo] = {
                "magnitud_pu": abs(v_pu),
                "magnitud_V": abs(v_pu) * vb,
                "angulo_grados": math.degrees(cmath.phase(v_pu)),
                "V_base": vb,
            }
        return res

    def __str__(self):
        return (f"ForwardBackwardSweep("
                f"nodos={self.n_nodos}, ramas={self.n_ramas}, "
                f"capas={len(self.capas)})")
