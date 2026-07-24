"""Coordinador distribuido via ZeroMQ.

Orquesta la simulacion distribuida entre:
  - PC Central (RelojZMQ + MasterClock)
  - N agentes BESS remotos conectados via TCP

Flujo por paso maestro:
  1. PC Central broadcast TICK (V_pcc, SoC_avg, demanda_w)
  2. Cada agente recibe TICK, computa P_ref localmente
  3. Cada agente envia MEASUREMENT (P_ref, SoC)
  4. PC Central recolecta, corre flujo de potencia
  5. PC Central computa SoC_avg global para el siguiente paso

Consenso centralizado (Phase 1): PC Central computa SoC_avg
y lo broadcast. No requiere ZeroMQ peer-to-peer entre agentes.
"""

import json
from CentralPC.master_clock import MasterClock
from CentralPC.reloj_zmq import RelojZMQ


class CoordinadorZMQ:
    """Orquestador distribuido de co-simulacion MAS sobre ZeroMQ."""

    def __init__(self, config_agentes=None, paso_maestro=0.1,
                 puerto=5555, modo_pc="A"):

        conf = config_agentes or self._config_default()
        self.paso_maestro = paso_maestro
        self.puerto = puerto
        self.tiempo = 0.0
        self.demanda_w = 0.0
        self.num_agentes = len(conf)
        self.ids_agentes = [c["id"] for c in conf]
        self.SoCs = {c["id"]: c.get("SoC_inicial", 0.5) for c in conf}
        self.SoC_avg = sum(self.SoCs.values()) / len(self.SoCs)
        self.P_refs = {c["id"]: 0.0 for c in conf}
        self.K_soc = {c["id"]: c.get("K_soc", 1.0) for c in conf}
        self.P_rated = {c["id"]: c.get("P_rated", 10000.0) for c in conf}

        self.pc = MasterClock(paso_maestro=paso_maestro, modo=modo_pc)
        self.reloj = RelojZMQ(puerto=puerto, paso_maestro=paso_maestro)
        self.V = None
        self.historico = []

    @staticmethod
    def _config_default():
        return [
            {"id": 1, "vecinos": [2],    "SoC_inicial": 0.8,
             "P_rated": 10000, "K_soc": 1.0},
            {"id": 2, "vecinos": [1, 3], "SoC_inicial": 0.5,
             "P_rated": 10000, "K_soc": 1.0},
            {"id": 3, "vecinos": [2],    "SoC_inicial": 0.3,
             "P_rated": 10000, "K_soc": 1.0},
        ]

    def ejecutar(self, tiempo_total, demanda_w=15000.0):
        self.reloj.iniciar()
        self.reloj.esperar_agentes(self.num_agentes, timeout=30.0)

        self.tiempo = 0.0
        self.demanda_w = demanda_w
        self.historico = []
        self.pc.tiempo = 0.0
        self.pc.historico = []

        paso = 0
        while self.tiempo < tiempo_total:
            t = self.tiempo

            V_pcc = {}
            if self.V is not None:
                for n in self.pc.nodos_red:
                    if n in self.ids_agentes:
                        V_pcc[str(n)] = round(float(abs(self.V[n])), 4)

            extras = {
                "SoC_avg": round(self.SoC_avg, 6),
                "SoCs": {str(k): round(v, 6)
                         for k, v in self.SoCs.items()},
            }
            self.reloj.enviar_tick(paso, t, V_pcc, demanda_w, extras)

            mediciones = self.reloj.recibir_mediciones(self.num_agentes)
            if not mediciones:
                print("[CoordinadorZMQ] No se recibieron mediciones. Abortando.")
                break

            for ag_id in self.ids_agentes:
                m = mediciones.get(ag_id, {})
                self.P_refs[ag_id] = m.get("P_ref", 0.0)
                self.SoCs[ag_id] = m.get("SoC", self.SoCs[ag_id])
                self.pc.registrar_inyeccion(ag_id, self.P_refs[ag_id], 0.0)

            self.SoC_avg = sum(self.SoCs.values()) / len(self.SoCs)
            self.V = self.pc.step()
            self.tiempo = self.pc.tiempo

            self.historico.append({
                "paso": paso,
                "tiempo": round(t, 3),
                "SoC_avg": round(self.SoC_avg, 6),
                "SoCs": {str(k): round(v, 6)
                         for k, v in self.SoCs.items()},
                "P_refs": {str(k): round(v, 1)
                           for k, v in self.P_refs.items()},
            })

            paso += 1
            if paso % 1000 == 0:
                disp = max(self.SoCs.values()) - min(self.SoCs.values())
                print(f"  paso {paso} t={self.tiempo:.1f}s "
                      f"SoC_avg={self.SoC_avg:.4f} "
                      f"disp={disp:.4f} "
                      f"agentes={len(mediciones)}")

        self.reloj.detener()
        print(f"\nCo-simulacion distribuida finalizada: "
              f"{paso} pasos en {tiempo_total:.1f}s")

    def _resumen(self):
        ids = sorted(self.SoCs.keys())
        out = []
        for ag_id in ids:
            out.append({
                "id": ag_id,
                "SoC": round(self.SoCs[ag_id], 4),
                "P_ref": round(self.P_refs[ag_id], 1),
            })
        return out


if __name__ == "__main__":
    config = [
        {"id": 1, "vecinos": [2],    "SoC_inicial": 0.8,
         "P_rated": 20000, "K_soc": 2.0},
        {"id": 2, "vecinos": [1, 3], "SoC_inicial": 0.5,
         "P_rated": 20000, "K_soc": 2.0},
        {"id": 3, "vecinos": [2],    "SoC_inicial": 0.3,
         "P_rated": 20000, "K_soc": 2.0},
    ]
    coord = CoordinadorZMQ(config, paso_maestro=0.1)
    coord.ejecutar(tiempo_total=10, demanda_w=15000)
