from MAS.AgenteBESS import AgenteBESS
from CentralPC.master_clock import MasterClock


class CoordinadorMAS:
    """Orquestador del sistema multi-agente.

    Coordina la simulacion distribuida entre:
      - N agentes BESS con consenso por difusion de tablas SoC
      - PC Central que resuelve el flujo de potencia
      - Demanda externa

    Flujo por paso maestro:
      1. Cada agente actualiza su tabla con SoC local
      2. Los agentes intercambian tablas con vecinos
      3. Cada agente computa SoC_avg de su tabla
      4. Cada agente calcula P_ref
      5. Registrar inyecciones en PC Central
      6. PC Central resuelve flujo de potencia
      7. Cada agente ejecuta su paso de bateria
    """

    def __init__(self, config_agentes=None, paso_maestro=0.1,
                 modo_pc="A"):
        conf = config_agentes or self._config_default()
        self.paso_maestro = paso_maestro
        self.tiempo = 0.0
        self.demanda_w = 0.0

        self.agentes = {}
        for c in conf:
            self.agentes[c["id"]] = AgenteBESS(
                id_agente=c["id"],
                vecinos=c.get("vecinos", []),
                num_agentes=len(conf),
                SoC_inicial=c.get("SoC_inicial", 0.5),
                capacidad_Ah=c.get("capacidad_Ah", 200.0),
                P_rated=c.get("P_rated", 10000.0),
                K_soc=c.get("K_soc", 1.0),
            )

        self.pc = MasterClock(paso_maestro=paso_maestro, modo=modo_pc)
        self.V = None
        self.historico = []

    @staticmethod
    def _config_default():
        return [
            {"id": 1, "vecinos": [2],    "SoC_inicial": 0.8, "P_rated": 10000},
            {"id": 2, "vecinos": [1, 3], "SoC_inicial": 0.5, "P_rated": 10000},
            {"id": 3, "vecinos": [2],    "SoC_inicial": 0.3, "P_rated": 10000},
        ]

    def step(self):
        t = self.tiempo
        step_num = int(round(t / self.paso_maestro))

        for ag in self.agentes.values():
            ag.consenso.actualizar_local(ag.SoC, step_num)

        for ronda in range(2):
            copias = {aid: a.obtener_tabla()
                      for aid, a in self.agentes.items()}
            steps_copias = {aid: a.obtener_steps()
                            for aid, a in self.agentes.items()}
            for ag in self.agentes.values():
                for vid in ag.consenso.vecinos:
                    if vid in self.agentes:
                        ag.consenso.recibir_vecino(
                            copias[vid], steps_copias[vid])

        for ag in self.agentes.values():
            ag.calcular_P_ref(self.demanda_w)
            self.pc.registrar_inyeccion(ag.id, ag.P_ref, 0.0)

        self.V = self.pc.step()

        for ag in self.agentes.values():
            ag.step(self.paso_maestro)

        for ag in self.agentes.values():
            ag.registrar_historico(t)

        self.tiempo = self.pc.tiempo

    def ejecutar(self, tiempo_total, demanda_w=15000.0):
        self.tiempo = 0.0
        self.historico = []
        self.demanda_w = demanda_w
        self.pc.tiempo = 0.0
        self.pc.historico = []

        for ag in self.agentes.values():
            ag.historico = []

        while self.tiempo < tiempo_total:
            self.step()

        print(f"Co-simulacion MAS finalizada: "
              f"{int(self.tiempo / self.paso_maestro)} pasos "
              f"en {tiempo_total:.1f}s | demanda={demanda_w:.0f}W")

    def _resumen(self):
        out = []
        for a in self.agentes.values():
            h = a.historico
            if h:
                out.append({
                    "id": a.id,
                    "SoC_ini": h[0]["SoC"],
                    "SoC_fin": h[-1]["SoC"],
                    "SoC_avg_fin": h[-1]["SoC_avg"],
                    "cobertura": h[-1]["cobertura"],
                    "pasos": len(h),
                })
        return out

    def _dispersion_SoC(self):
        so = {a.id: a.SoC for a in self.agentes.values()}
        return max(so.values()) - min(so.values())


def _test_mas():
    config = [
        {"id": 1, "vecinos": [2],    "SoC_inicial": 0.8, "capacidad_Ah": 5,
         "P_rated": 20000, "K_soc": 2.0},
        {"id": 2, "vecinos": [1, 3], "SoC_inicial": 0.5, "capacidad_Ah": 5,
         "P_rated": 20000, "K_soc": 2.0},
        {"id": 3, "vecinos": [2],    "SoC_inicial": 0.3, "capacidad_Ah": 5,
         "P_rated": 20000, "K_soc": 2.0},
    ]

    coord = CoordinadorMAS(config_agentes=config, paso_maestro=0.1)
    coord.ejecutar(tiempo_total=300, demanda_w=15000)

    r = coord._resumen()
    print(f"{'ID':>3} {'SoC_ini':>8} {'SoC_fin':>8} {'SoC_avg':>8} {'Cob':>4} {'Pasos':>6}")
    for e in r:
        print(f"{e['id']:>3} {e['SoC_ini']:>8.3f} "
              f"{e['SoC_fin']:>8.3f} {e['SoC_avg_fin']:>8.3f} "
              f"{e['cobertura']:>4} {e['pasos']:>6}")

    V = {n: f"{abs(coord.V[n]):.4f}" for n in coord.pc.nodos_red}
    print(f"\nTensiones finales [pu]: {V}")
    print(f"Dispersion SoC final: {coord._dispersion_SoC():.4f}")


if __name__ == "__main__":
    _test_mas()
