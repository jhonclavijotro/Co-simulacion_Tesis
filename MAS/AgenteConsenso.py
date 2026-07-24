class AgenteConsenso:
    """Agente con difusion de informacion para consenso distribuido.

    Cada agente mantiene una tabla {(id, step): SoC} con timestamps.
    Al recibir una tabla vecina, solo acepta entradas con step MAYOR
    al que ya conoce. Esto evita que valores stale sobrescriban
    valores mas recientes.

    El step es el numero de paso maestro en que el agente actualizo
    su propio SoC. Un agente solo es autoritativo para su propia
    entrada, y marca cada actualizacion con el step actual.
    """

    def __init__(self, id_agente, vecinos, num_agentes):
        self.id = id_agente
        self.vecinos = list(vecinos)
        self.n = num_agentes
        self.tabla = {id_agente: 0.0}
        self.steps = {id_agente: 0}

    def init_tabla(self, SoC_inicial):
        self.tabla[self.id] = SoC_inicial
        self.steps[self.id] = 0

    def actualizar_local(self, SoC, step):
        self.tabla[self.id] = SoC
        self.steps[self.id] = step

    def recibir_vecino(self, tabla_vecina, steps_vecinos):
        for k in tabla_vecina:
            v = tabla_vecina[k]
            sv = steps_vecinos[k]
            if k != self.id and (k not in self.steps or sv > self.steps[k]):
                self.tabla[k] = v
                self.steps[k] = sv

    def obtener_tabla(self):
        return dict(self.tabla)

    def obtener_steps(self):
        return dict(self.steps)

    def promedio_global(self):
        if not self.tabla:
            return 0.0
        return sum(self.tabla.values()) / len(self.tabla)

    @property
    def cobertura(self):
        return len(self.tabla)

    def __str__(self):
        return (f"AgenteConsenso(id={self.id}, "
                f"vecinos={self.vecinos}, "
                f"cobertura={self.cobertura}/{self.n})")
