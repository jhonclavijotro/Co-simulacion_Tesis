import csv
import time as time_mod
from CentralPC.solver_sweep import ForwardBackwardSweep


class MasterClock:
    """Reloj maestro que coordina la co-simulacion multitasa.

    En cada paso maestro (tipicamente 100-500 ms), el reloj:
      1. Recibe las inyecciones de potencia de los nodos de generacion
         y demanda (via ZeroMQ en produccion, via diccionario en local)
      2. Ejecuta el Forward-Backward Sweep para resolver la red
      3. Publica las tensiones nodales calculadas

    Esta implementacion local ejecuta en un solo proceso para propositos
    de prueba y desarrollo. En produccion, los nodos se comunican via
    ZeroMQ desde contenedores Docker independientes.
    """

    def __init__(self, archivo_red="CentralPC/red_ejemplo.csv",
                 paso_maestro=0.1):
        self.sweep = ForwardBackwardSweep(archivo_red)
        self.paso_maestro = paso_maestro
        self.tiempo = 0.0
        self.nodos_red = list(range(self.sweep.n_nodos))
        self.inyecciones = {n: (0.0, 0.0) for n in self.nodos_red if n != 0}
        self.V = None
        self.historico = []

    def registrar_inyeccion(self, nodo, P, Q):
        """Registra la inyeccion de un nodo en la red.

        Parametros:
            nodo: Identificador del nodo (int)
            P: Potencia activa inyectada (+) o consumida (-) [W]
            Q: Potencia reactiva inyectada (+) o consumida (-) [VAR]
        """
        self.inyecciones[nodo] = (P, Q)

    def step(self):
        """Ejecuta un paso de co-simulacion.

        Resuelve el flujo de potencia con las inyecciones actuales.
        """
        self.V, convergio, it = self.sweep.resolver(self.inyecciones)
        if not convergio:
            print(f"  [ADVERTENCIA] No convergio en iteracion "
                  f"t={self.tiempo:.3f}s")
        self.tiempo = round(self.tiempo + self.paso_maestro, 3)
        return self.V

    def obtener_tension_nodal(self, nodo):
        """Retorna la tension de un nodo especifico.

        Retorna:
            dict con magnitud [pu], angulo [grados], real, imag, V [V]
        """
        if self.V is None:
            return None
        Vn = self.V[nodo]
        return {
            "magnitud_pu": abs(Vn),
            "angulo_grados": __import__("math").degrees(
                __import__("cmath").phase(Vn)),
            "magnitud_V": abs(Vn) * 110.0,
        }

    def ejecutar(self, tiempo_total, generadores=None):
        """Ejecuta una co-simulacion completa.

        En modo local, los generadores se simulan internamente.
        En produccion, recibiran datos via ZeroMQ.

        Parametros:
            tiempo_total: Duracion de la simulacion [s]
            generadores: dict opcional con generadores simulados
        """
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
            })

        print(f"Co-simulacion finalizada: "
              f"{len(self.historico)} pasos en {tiempo_total:.1f}s")


class GeneradorSimulado:
    """Generador de prueba para la co-simulacion local.

    Implementa perfiles simples de inyeccion P, Q para verificar
    el funcionamiento del solucionador de red.
    """

    def __init__(self, P_base=10000.0, Q_base=0.0, nodo=1):
        self.P_base = P_base
        self.Q_base = Q_base
        self.nodo = nodo

    def obtener_inyeccion(self, t):
        if t < 2:
            return self.P_base * 0.5, self.Q_base
        elif t < 5:
            return self.P_base * 0.8, self.Q_base
        elif t < 8:
            return self.P_base * 1.0, self.Q_base
        else:
            return self.P_base * 0.6, self.Q_base


if __name__ == "__main__":
    reloj = MasterClock(archivo_red="CentralPC/red_ejemplo.csv",
                        paso_maestro=0.1)

    generador_1 = GeneradorSimulado(P_base=20000, nodo=1)
    generador_2 = GeneradorSimulado(P_base=10000, nodo=2)
    generador_3 = GeneradorSimulado(P_base=5000, nodo=3)

    reloj.ejecutar(tiempo_total=10, generadores={
        1: generador_1,
        2: generador_2,
        3: generador_3,
    })

    for entry in reloj.historico[::20]:
        t = entry["tiempo"]
        Vs = entry["V"]
        print(f"t={t:5.2f}s | V0={Vs[0]:.4f} V1={Vs[1]:.4f} "
              f"V2={Vs[2]:.4f} V3={Vs[3]:.4f} [pu]")
