import csv
from typing import Any, Dict, List, Optional

from CentralPC.solver_sweep import ForwardBackwardSweep
from CentralPC.solver_sensitivity import SensitivitySolver


class MasterClock:
    """Reloj maestro que coordina la co-simulacion multitasa."""

    def __init__(self, archivo_red: str = "CentralPC/red_ejemplo.csv",
                 paso_maestro: float = 0.1, modo: str = "A") -> None:
        self.modo: str = modo.upper()
        self.sweep: ForwardBackwardSweep = ForwardBackwardSweep(archivo_red)
        self.sensitivity: SensitivitySolver = SensitivitySolver(archivo_red)
        self.paso_maestro: float = paso_maestro
        self.tiempo: float = 0.0
        self.nodos_red: List[int] = list(range(self.sweep.n_nodos))
        self.inyecciones: Dict[int, tuple] = {
            n: (0.0, 0.0) for n in self.nodos_red if n != 0
        }
        self.V: Optional[Any] = None
        self.historico: List[Dict[str, Any]] = []
        self._calibrado: bool = False

    def registrar_inyeccion(self, nodo: int, P: float, Q: float) -> None:
        self.inyecciones[nodo] = (P, Q)

    def step(self) -> Any:
        if self.modo == "B":
            if not self._calibrado and any(self.inyecciones.values()):
                self.sensitivity.calibrar(self.inyecciones)
                self._calibrado = True
            V, convergio, it = self.sensitivity.resolver(self.inyecciones)
        else:
            V, convergio, it = self.sweep.resolver(self.inyecciones)
        self.V = V
        if not convergio:
            print(f"  [ADVERTENCIA] No convergio en iteracion "
                  f"t={self.tiempo:.3f}s")
        self.tiempo = round(self.tiempo + self.paso_maestro, 3)
        return self.V

    def obtener_tension_nodal(self, nodo: int) -> Optional[Dict[str, float]]:
        if self.V is None:
            return None
        Vn = self.V[nodo]
        return {
            "magnitud_pu": abs(Vn),
            "angulo_grados": __import__("math").degrees(
                __import__("cmath").phase(Vn)),
            "magnitud_V": abs(Vn) * 110.0,
        }

    def ejecutar(self, tiempo_total: float,
                 generadores: Optional[Dict[int, Any]] = None) -> None:
        self.tiempo = 0.0
        self.historico = []
        paso_red = self.paso_maestro

        while self.tiempo < tiempo_total:
            t = self.tiempo
            if generadores:
                for nodo, gen in generadores.items():
                    P, Q = gen.obtener_inyeccion(t)
                    self.registrar_inyeccion(nodo, P, Q)
            self.step()
            self.historico.append({
                "tiempo": t,
                "V": {n: abs(self.V[n]) for n in self.nodos_red},
                "modo": self.modo,
            })

        print(f"Co-simulacion [Modo {self.modo}] finalizada: "
              f"{len(self.historico)} pasos en {tiempo_total:.1f}s")


class GeneradorSimulado:
    def __init__(self, P_base: float = 10000.0, Q_base: float = 0.0,
                 nodo: int = 1) -> None:
        self.P_base = P_base
        self.Q_base = Q_base
        self.nodo = nodo

    def obtener_inyeccion(self, t: float) -> tuple:
        if t < 2:
            return self.P_base * 0.5, self.Q_base
        elif t < 5:
            return self.P_base * 0.8, self.Q_base
        elif t < 8:
            return self.P_base * 1.0, self.Q_base
        else:
            return self.P_base * 0.6, self.Q_base


def _comparar_modos() -> None:
    generadores: Dict[int, GeneradorSimulado] = {
        1: GeneradorSimulado(P_base=15000, nodo=1),
        2: GeneradorSimulado(P_base=8000, nodo=2),
        3: GeneradorSimulado(P_base=5000, nodo=3),
    }
    for modo in ["A", "B"]:
        reloj = MasterClock(archivo_red="CentralPC/red_ejemplo.csv",
                            paso_maestro=0.1, modo=modo)
        reloj.ejecutar(tiempo_total=10, generadores=generadores)
        for entry in reloj.historico[::20]:
            t = entry["tiempo"]
            Vs = entry["V"]
            print(f"[Modo {modo}] t={t:5.2f}s | "
                  f"V0={Vs[0]:.4f} V1={Vs[1]:.4f} "
                  f"V2={Vs[2]:.4f} V3={Vs[3]:.4f} [pu]")
        print()


if __name__ == "__main__":
    _comparar_modos()
