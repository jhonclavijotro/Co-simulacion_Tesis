from typing import Dict, List


class AgenteConsenso:
    """Agente con difusion de informacion para consenso distribuido."""

    def __init__(self, id_agente: int, vecinos: List[int], num_agentes: int) -> None:
        self.id: int = id_agente
        self.vecinos: List[int] = list(vecinos)
        self.n: int = num_agentes
        self.tabla: Dict[int, float] = {id_agente: 0.0}
        self.steps: Dict[int, int] = {id_agente: 0}

    def init_tabla(self, SoC_inicial: float) -> None:
        self.tabla[self.id] = SoC_inicial
        self.steps[self.id] = 0

    def actualizar_local(self, SoC: float, step: int) -> None:
        self.tabla[self.id] = SoC
        self.steps[self.id] = step

    def recibir_vecino(self, tabla_vecina: Dict[int, float],
                       steps_vecinos: Dict[int, int]) -> None:
        for k in tabla_vecina:
            v = tabla_vecina[k]
            sv = steps_vecinos[k]
            if k != self.id and (k not in self.steps or sv > self.steps[k]):
                self.tabla[k] = v
                self.steps[k] = sv

    def obtener_tabla(self) -> Dict[int, float]:
        return dict(self.tabla)

    def obtener_steps(self) -> Dict[int, int]:
        return dict(self.steps)

    def promedio_global(self) -> float:
        if not self.tabla:
            return 0.0
        return sum(self.tabla.values()) / len(self.tabla)

    @property
    def cobertura(self) -> int:
        return len(self.tabla)

    def __str__(self) -> str:
        return (f"AgenteConsenso(id={self.id}, "
                f"vecinos={self.vecinos}, "
                f"cobertura={self.cobertura}/{self.n})")
