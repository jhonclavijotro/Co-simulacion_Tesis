from MAS.AgenteConsenso import AgenteConsenso
from MAS.BESS_simplificado import BateriaSimplificada


class AgenteBESS:
    """Nodo BESS con consenso distribuido para co-simulacion MAS."""

    def __init__(self, id_agente, vecinos, num_agentes,
                 V_nominal=48.0, capacidad_Ah=200.0, SoC_inicial=0.5,
                 P_rated=10000.0, K_soc=1.0):
        self.id = id_agente
        self.P_rated = P_rated
        self.K_soc = K_soc
        self.num_agentes = num_agentes

        self.bateria = BateriaSimplificada(
            V_nominal=V_nominal, capacidad_Ah=capacidad_Ah,
            SoC_inicial=SoC_inicial, N_serie=10
        )

        self.consenso = AgenteConsenso(
            id_agente, vecinos, num_agentes
        )
        self.consenso.init_tabla(SoC_inicial)

        self.P_ref = 0.0
        self.historico = []

    @property
    def SoC(self):
        return self.bateria.SoC

    @property
    def SoC_avg(self):
        return self.consenso.promedio_global()

    def obtener_tabla(self):
        return self.consenso.obtener_tabla()

    def obtener_steps(self):
        return self.consenso.obtener_steps()

    def calcular_P_ref(self, P_total_demanda):
        fraccion = 1.0 / self.num_agentes
        desvio = self.SoC - self.SoC_avg
        fraccion += self.K_soc * desvio
        self.P_ref = P_total_demanda * fraccion
        self.P_ref = max(-self.P_rated, min(self.P_rated, self.P_ref))
        return self.P_ref

    def step(self, dt, V_pcc=None, P_total_demanda=None):
        self.bateria.step(dt, self.P_ref, V_pcc=V_pcc)

    def registrar_historico(self, tiempo):
        self.historico.append({
            "tiempo": tiempo,
            "id": self.id,
            "SoC": self.SoC,
            "SoC_avg": self.SoC_avg,
            "cobertura": self.consenso.cobertura,
            "P_ref": self.P_ref,
            "P_real": self.bateria.P_real,
        })

    def __str__(self):
        return (f"AgenteBESS(id={self.id}, SoC={self.SoC:.3f}, "
                f"SoC_avg={self.SoC_avg:.3f}, P_ref={self.P_ref:.0f}W)")
