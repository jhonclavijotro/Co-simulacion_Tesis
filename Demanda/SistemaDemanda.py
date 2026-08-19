import csv
from Demanda.PerfilDemanda import PerfilDemanda


class SistemaDemanda:
    """Nodo de demanda electrica (carga).

    A diferencia de los nodos de generacion, este nodo no tiene
    dinamica propia. Simplemente lee los perfiles de potencia
    activa (P) y reactiva (Q) y los pone a disposicion del
    solucionador de red (PC Central).

    Cuando se integre con el sistema multi-agente, este nodo
    reportara su demanda al agente de consenso para que participe
    en el balance de potencia de la microrred.
    """

    def __init__(self, archivo_csv=None, P_nominal=10000.0, Q_nominal=0.0):
        self.perfil = PerfilDemanda(
            archivo_csv=archivo_csv,
            P_nominal=P_nominal,
            Q_nominal=Q_nominal
        )
        self.sample_time = 0.001
        self.datos = []
        self.contexto = {
            "time": 0.0,
            "P_demand": P_nominal,
            "Q_demand": Q_nominal,
        }

    def step(self, dt=0.001, V_pcc=None, setpoints=None):
        """Ejecuta un paso del nodo de demanda.

        Lee la demanda actual del perfil y actualiza el contexto.

        Parametros:
            dt: Paso de tiempo [s]
            V_pcc: No utilizado (compatibilidad con interfaz comun)
            setpoints: No utilizado (compatibilidad con interfaz comun)

        Retorna:
            Copia del diccionario de contexto con el estado actualizado.
        """
        ctx = self.contexto
        P, Q = self.perfil.obtener_en_tiempo(ctx["time"])
        ctx["P_demand"] = P
        ctx["Q_demand"] = Q
        ctx["time"] = round(ctx["time"] + dt, 3)
        return dict(ctx)

    def ejecutar(self, tiempo_simulacion=15):
        """Ejecuta la simulacion del perfil de demanda.

        Parametros:
            tiempo_simulacion: Duracion total de la simulacion [s]
        """
        ctx = self.contexto
        while ctx["time"] < tiempo_simulacion:
            try:
                resultado = self.step(self.sample_time)
                self.datos.append([
                    resultado["time"],
                    resultado["P_demand"],
                    resultado["Q_demand"],
                ])
            except Exception as e:
                print(f"Error en t={ctx['time']:.3f}s: {e}")
                break

        header = ["time", "P_demand", "Q_demand"]
        with open("resultados_demanda.csv", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(self.datos)

        print("Simulacion de demanda finalizada. "
              "Datos guardados en resultados_demanda.csv")


if __name__ == "__main__":
    sistema = SistemaDemanda(P_nominal=15000.0)
    sistema.ejecutar(tiempo_simulacion=15)
