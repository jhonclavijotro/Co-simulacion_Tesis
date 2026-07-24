import csv
from Hidrica.TurbinaHidrocinetica import TurbinaHidrocinetica
from common.PMSG import SistemaPMG
from common.Rectificador import Rectificador
from common.Transformadas import Transformadas
from common.RedTrifasica import RedTrifasica
from common.GridInverter import GridConnectedInverter


class SistemaHidrico:
    """Sistema completo de generacion hidrocinetica conectado a red.

    Adaptado del sistema eolico (SistemaEolico). Comparte con este los
    subsistemas de conversion: PMSG, rectificador, inversor trifasico
    y PLL. La unica diferencia es la turbina (TurbinaHidrocinetica) que
    utiliza densidad del agua (1000 kg/m3) en lugar de la del aire.

    TODO: Cuando se complete la Fase 2 (DRY), los componentes compartidos
    (PMSG, Rectificador, Transformadas, RedTrifasica, GridInverter) se
    migraran al directorio comun 'common/'.
    """

    def __init__(self):
        """Inicializa todos los subsistemas y el estado interno de la simulacion."""
        self.turbina = TurbinaHidrocinetica(R=1.5, B=0.0)
        self.sistema_pmg = SistemaPMG(relacion=4.0)
        self.rectificador = Rectificador()
        self.redtrifasica = RedTrifasica()
        self.transformadas = Transformadas()
        self.inversor = GridConnectedInverter()
        self.datos = []
        self.sample_time = 0.001
        self.Vc = None
        self.contexto = {
            "time": 0.0,
            "Wr": 0.0,
            "Vc": 2.0,
            "Idi": 0.0,
            "Iq": 0.0,
            "Vqi": 0.0,
            "theta0": 0.0,
            "Vdi": 0.0,
            "Fsys": 0.0,
            "Vq": 0.0,
            "Te": 0.0,
            "Tg": 0.0,
            "Tm": 0.0,
            "Wg": 0.0,
            "Vdc": 300.0,
            "Pdc_in": 0.0,
            "Pdc_out": 0.0,
            "Vdt": 0.0,
        }

    def _perfil_corriente(self, t):
        """Genera un perfil de velocidad de corriente variable en el tiempo.

        Simula variaciones tipicas de caudal en un rio o canal.
        """
        if t < 5:
            return 2.0
        elif t < 10:
            return 2.0 + (3.5 - 2.0) * ((t - 5) / 5.0)
        elif t < 15:
            return 3.5
        elif t < 20:
            return 3.5 - (3.5 - 1.8) * ((t - 15) / 5.0)
        else:
            return 1.8

    def step(self, dt=0.001, V_pcc=None, setpoints=None):
        """Ejecuta un paso de integracion de todo el sistema hidrocinetico.

        Parametros:
            dt: Paso de tiempo [s]
            V_pcc: Tension en el punto de acoplamiento comun (PCC) [V]
            setpoints: Diccionario opcional con consignas externas

        Retorna:
            Copia del diccionario de contexto con el estado actualizado.
        """
        ctx = self.contexto

        if setpoints:
            if "Q_ref_kvar" in setpoints:
                ctx["Pq"] = setpoints["Q_ref_kvar"] * 1000.0

        Vc = self.Vc if self.Vc is not None else self._perfil_corriente(ctx["time"])
        ctx["Vc"] = Vc

        Tm = self.turbina.calcular_torque(ctx["Wr"], Vc)
        ctx["Tm"] = Tm

        datos_pmg = self.sistema_pmg.calcular_sistema(ctx["Vq"], ctx["Tm"], dt)
        ctx["Wg"] = datos_pmg["Wg"]
        ctx["Tg"] = datos_pmg["Tg"]
        ctx["Wr"] = datos_pmg["Wr"]
        ctx["Iq"] = datos_pmg["Iq"]

        Vdc_new, Vq_rect, Pdc_in, Pdc_out = self.rectificador.ejecutar(
            Vc, ctx["Wr"], ctx["Iq"], ctx["Idi"], ctx["Wg"], ctx["Vdc"], dt)
        ctx["Vdc"] = Vdc_new
        ctx["Vq"] = Vq_rect
        ctx["Pdc_in"] = Pdc_in
        ctx["Pdc_out"] = Pdc_out

        Pw, Pq, Idi, Iqi, Vdt, Idiref = self.inversor.step(
            ctx["Vdc"], ctx["Vdi"], ctx["Vqi"], ctx["theta0"], ctx["Iq"], dt)
        ctx["Idi"] = Idi
        ctx["Iqi"] = Iqi
        ctx["Vdt"] = Vdt
        ctx["Pw"] = Pw
        ctx["Pq"] = Pq

        if V_pcc is not None:
            Va, Vb, Vc = V_pcc, 0.0, 0.0
        else:
            Va, Vb, Vc = self.redtrifasica.step(ctx["time"], Pw, Pq)

        Valpha, Vbeta, theta0, Vq_out, Vd_out, Fsys = \
            self.transformadas.aplicar_transformadas([Va, Vb, Vc], ctx["Vqi"])
        ctx["theta0"] = theta0
        ctx["Vqi"] = Vq_out
        ctx["Vdi"] = Vd_out
        ctx["Fsys"] = Fsys

        ctx["time"] = round(ctx["time"] + dt, 3)
        return dict(ctx)

    def ejecutar(self, tiempo_simulacion=25):
        """Ejecuta la simulacion durante un intervalo de tiempo especificado.

        Parametros:
            tiempo_simulacion: Duracion total de la simulacion [s]
        """
        ctx = self.contexto
        while ctx["time"] < tiempo_simulacion:
            try:
                resultado = self.step(self.sample_time)
                self.datos.append([
                    resultado["time"], resultado["Wr"], resultado["Tm"], resultado["Wg"],
                    resultado["Tg"], resultado["Vq"], resultado["Iq"], resultado["Vdc"],
                    resultado["Pdc_in"], resultado["Vdt"], resultado["Idi"],
                    resultado.get("Idiref", 0), resultado["Pdc_out"],
                    resultado["Vdi"], resultado["Vqi"], resultado["Fsys"],
                    resultado["Pw"], resultado["Pq"], resultado["Vc"],
                    resultado["Vdi"], resultado["Vqi"], resultado["Fsys"],
                    resultado.get("Valpha", 0), resultado.get("Vbeta", 0),
                ])
            except Exception as e:
                print(f"Error en t={ctx['time']:.3f}s: {e}")
                break

        header = ["Tiempo", "Wr", "Tm", "Wg", "Tg",
                   "Vq", "Iq", "Vdc", "Pdc_in",
                   "Vdt", "Idi", "Idiref", "Pdc_out",
                   "Vd_red", "Vq_red", "Fsys_red", "Pw", "Pq", "Vc",
                   "Va", "Vb", "Vc", "Valpha", "Vbeta"]
        with open("resultados_hidrico.csv", "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(header)
            writer.writerows(self.datos)

        print("Simulacion hidrocinetica finalizada. Datos guardados en resultados_hidrico.csv")


if __name__ == "__main__":
    sistema = SistemaHidrico()
    sistema.ejecutar()
