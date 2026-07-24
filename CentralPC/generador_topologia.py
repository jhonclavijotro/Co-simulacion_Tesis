"""Generador parametrico de topologias de red radial.

Crea archivos CSV de configuracion de red para N nodos de generacion
y M nodos virtuales de demanda, con topologia radial arbolada.
"""

import csv
import math
import os


class GeneradorTopologia:
    """Genera topologia radial parametrica N+M."""

    def __init__(self, N=4, M=2, V_base=110.0, S_base=1e6):
        self.N = N
        self.M = M
        self.V_base = V_base
        self.S_base = S_base
        self.total_nodos = 1 + N + M

    def generar_radial(self, r_ohm_km=0.5, x_ohm_km=0.3, d_km=0.1):
        """Genera topologia radial: nodo 0 (slack) como raiz, ramas hacia N+M nodos.

        Distribucion:
          - Nodo 0: slack (subestacion)
          - Nodos 1..N: generacion
          - Nodos N+1..N+M: demanda virtual

        Retorna:
            list[dict] ramas: [{from_node, to_node, R_ohm, X_ohm, length_m}]
        """
        ramas = []
        if self.total_nodos <= 1:
            return ramas

        # Cada nodo se conecta al nodo anterior (cadena radial simple)
        for i in range(1, self.total_nodos):
            rama = {
                "from_node": i - 1,
                "to_node": i,
                "R_ohm": r_ohm_km * d_km,
                "X_ohm": x_ohm_km * d_km,
                "length_m": d_km * 1000,
            }
            ramas.append(rama)

        return ramas

    def generar_mallada(self, r_ohm_km=0.5, x_ohm_km=0.3, d_km=0.1):
        """Genera topologia debilmente mallada (anillo).

        N nodos de generacion en anillo, M virtuales como ramas.
        """
        ramas = []
        if self.total_nodos <= 1:
            return ramas

        # Anillo entre nodos 0..N
        for i in range(self.N + 1):
            j = (i + 1) % (self.N + 1)
            rama = {
                "from_node": i,
                "to_node": j,
                "R_ohm": r_ohm_km * d_km,
                "X_ohm": x_ohm_km * d_km,
                "length_m": d_km * 1000,
            }
            # Evitar duplicados en el cierre del anillo
            if any(r["from_node"] == j and r["to_node"] == i for r in ramas):
                continue
            ramas.append(rama)

        # Nodos virtuales colgando del ultimo nodo de generacion
        for m in range(1, self.M + 1):
            idx = self.N + m
            padre = self.N if m == 1 else idx - 1
            rama = {
                "from_node": padre,
                "to_node": idx,
                "R_ohm": r_ohm_km * d_km,
                "X_ohm": x_ohm_km * d_km,
                "length_m": d_km * 1000,
            }
            ramas.append(rama)

        return ramas

    def guardar_csv(self, archivo, ramas=None, modo="radial"):
        if ramas is None:
            if modo == "radial":
                ramas = self.generar_radial()
            else:
                ramas = self.generar_mallada()

        os.makedirs(os.path.dirname(archivo) or ".", exist_ok=True)
        with open(archivo, "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["from_node", "to_node", "R_ohm", "X_ohm", "length_m"]
            )
            writer.writeheader()
            writer.writerows(ramas)

        n = self.total_nodos
        print(f"[GeneradorTopologia] {modo}: {n} nodos "
              f"({self.N} gen + {self.M} dem), "
              f"{len(ramas)} ramas -> {archivo}")
        return ramas

    def resumen(self):
        return {
            "N": self.N,
            "M": self.M,
            "total_nodos": self.total_nodos,
            "ids_generacion": list(range(1, self.N + 1)),
            "ids_demanda": list(range(self.N + 1, self.total_nodos)),
        }
