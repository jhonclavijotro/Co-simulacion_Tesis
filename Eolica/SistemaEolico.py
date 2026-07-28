import csv
from Eolica.Aerogenerador import Aerogenerador
from common.PMSG import SistemaPMG
from common.Rectificador import Rectificador
from common.Transformadas import Transformadas
from common.RedTrifasica import RedTrifasica
from common.GridInverter import GridConnectedInverter
from common.GraficadorEolico import graficar_resultados


class SistemaEolico:
    """Sistema completo de generacion eolica conectado a red.

    Integra el aerogenerador, generador PMSG, rectificador, inversor
    trifasico y PLL para sincronizacion con la red electrica.
    """

    def __init__(self):
        """Inicializa todos los subsistemas y el estado interno de la simulacion."""
        self.aerogenerador = Aerogenerador(R=2.5, B=8.0)
        self.sistema_pmg = SistemaPMG(relacion=4.0)
        self.rectificador = Rectificador()
        self.redtrifasica = RedTrifasica()
        self.transformadas = Transformadas()
        self.inversor = GridConnectedInverter()
        self.datos = []
        self.sample_time = 0.001
        self.Ws = None
        self.contexto = {
            "time": 0.0,
            "Wr": 0.0,
            "Ws": 14.0,
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

    def _perfil_viento(self, t):
        """Genera un perfil de viento variable en el tiempo para la simulacion."""
        if t < 4:
            return 8.0
        elif t < 9:
            return 8.0 + (12.0 - 8.0) * ((t - 4) / 5.0)
        elif t < 10:
            return 12.0 - (12.0 - 10.0) * ((t - 9.9) / 1.0)
        elif t < 15:
            return 10.0
        elif t < 20:
            return 10.0 + (12.0 - 10.0) * ((t - 15) / 5.0)
        else:
            return 12.0

    def step(self, dt=0.001, V_pcc=None, setpoints=None):
        """Ejecuta un paso de integracion de todo el sistema eolico.

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

        Ws = self.Ws if self.Ws is not None else self._perfil_viento(ctx["time"])
        ctx["Ws"] = Ws

        Tm = self.aerogenerador.calcular_torque(ctx["Wr"], Ws)
        ctx["Tm"] = Tm

        datos_pmg = self.sistema_pmg.calcular_sistema(ctx["Vq"], ctx["Tm"], dt)
        ctx["Wg"] = datos_pmg["Wg"]
        ctx["Tg"] = datos_pmg["Tg"]
        ctx["Wr"] = datos_pmg["Wr"]
        ctx["Iq"] = datos_pmg["Iq"]

        Vdc_new, Vq_rect, Pdc_in, Pdc_out = self.rectificador.ejecutar(
            Ws, ctx["Wr"], ctx["Iq"], ctx["Idi"], ctx["Wg"], ctx["Vdc"], dt)
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
                    resultado["Pw"], resultado["Pq"], resultado["Ws"],
                    resultado["Vdi"], resultado["Vqi"], resultado["Fsys"],
                    resultado.get("Valpha", 0), resultado.get("Vbeta", 0),
                ])
            except Exception as e:
                print(f"Error during simulation: {e}")
                break

        header = ["Tiempo", "Wr", "Tm", "Wg", "Tg",
                   "Vq", "Iq", "Vdc", "Pdc_in",
                   "Vdt", "Idi", "Idiref", "Pdc_out",
                   "Vd_red", "Vq_red", "Fsys_red", "Pw", "Pq", "Ws",
                   "Va", "Vb", "Vc", "Valpha", "Vbeta"]
        with open("resultados.csv", "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(header)
            writer.writerows(self.datos)

        graficar_resultados()


if __name__ == "__main__":
    sistema = SistemaEolico()
    sistema.ejecutar()
