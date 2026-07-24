import csv
from Diesel.Diesel import controlDiesel, modeloDiesel
from common.PMSG import PMSG, Gearbox
from common.Rectificador import Rectificador
from common.GridInverter import GridConnectedInverter
from common.Transformadas import Transformadas


class SistemaDiesel:
    """Sistema completo de generacion diesel conectado a red.

    Integra el motor diesel con su control de velocidad, generador PMSG,
    rectificador, inversor trifasico y PLL para sincronizacion.
    """

    def __init__(self):
        """Inicializa todos los subsistemas y el estado interno de la simulacion."""
        self.sample_time = 0.001
        self.pmsg = PMSG(metodo="statespace")
        self.gearbox = Gearbox(relacion=4.0)
        self.rectificador = Rectificador()
        self.inversor = GridConnectedInverter()
        self.transformadas = Transformadas()

        self.E1 = 0.0
        self.y1 = 0.0

        self.contexto = {
            "time": 0.0,
            "Wr": 0.0,
            "pref": 1100,
            "Tm": 0.0,
            "Wg": 0.0,
            "Iq": 0.0,
            "Vq": 0.0,
            "Vdc": 300.0,
            "Vdi": 0.0,
            "Vqi": 0.0,
            "theta0": 0.0,
        }
        self.datos = []

    def step(self, dt=0.001, V_pcc=None, setpoints=None):
        """Ejecuta un paso de integracion de todo el sistema diesel.

        Parametros:
            dt: Paso de tiempo [s]
            V_pcc: Tension en el punto de acoplamiento comun (PCC) [V]
            setpoints: Diccionario opcional con consignas externas

        Retorna:
            Copia del diccionario de contexto con el estado actualizado.
        """
        ctx = self.contexto

        if setpoints:
            if "pref_ajuste" in setpoints:
                ctx["pref"] = setpoints["pref_ajuste"]
            if "Q_ref_kvar" in setpoints:
                ctx["Pq"] = setpoints["Q_ref_kvar"] * 1000.0

        E = ctx["pref"] - ctx["Wr"]
        F = controlDiesel(E, self.E1, self.y1)
        self.y1 = F
        self.E1 = E

        tv = [0, dt]
        Tm_array = modeloDiesel(F, tv)
        Tm_engine = float(Tm_array[-1]) if hasattr(Tm_array, '__len__') else float(Tm_array)

        Tg, Wr_new = self.gearbox.convertir_torque_velocidad(Tm_engine, ctx["Wg"])
        ctx["Tm"] = Tg
        ctx["Wr"] = Wr_new

        Iq_pmsg, Wg_pmsg = self.pmsg.calcular_respuesta(ctx["Vq"], Tm_engine, dt)
        ctx["Iq"] = Iq_pmsg
        ctx["Wg"] = Wg_pmsg

        Vdc_new, Vq_rect, Pdc_in, Pdc_out = self.rectificador.ejecutar(
            ctx["pref"], ctx["Wr"], ctx["Iq"], 0.0, ctx["Wg"], ctx["Vdc"], dt)
        ctx["Vdc"] = Vdc_new
        ctx["Vq"] = Vq_rect

        Pw, Pq, Idi, Iqi, Vdt, Idiref = self.inversor.step(
            ctx["Vdc"], ctx["Vdi"], ctx["Vqi"], ctx["theta0"], ctx["Iq"], dt)
        ctx["Vdi"] = Vdt
        ctx["Vqi"] = Iqi

        Va, Vb, Vc = ctx["Vdi"], ctx["Vqi"], 0.0
        Valpha, Vbeta, theta0, Vq_out, Vd_out, Fsys = \
            self.transformadas.aplicar_transformadas([Va, Vb, Vc], ctx["Vqi"])
        ctx["theta0"] = theta0
        ctx["Fsys"] = Fsys

        ctx["time"] = round(ctx["time"] + dt, 3)
        return dict(ctx)

    def ejecutar(self, tiempo_simulacion=25):
        ctx = self.contexto
        while ctx["time"] < tiempo_simulacion:
            try:
                resultado = self.step(self.sample_time)
                self.datos.append([
                    resultado["time"], resultado["pref"], resultado["Wr"], resultado["Tm"],
                    resultado["Wg"], resultado["Iq"], resultado["Vq"], resultado["Vdc"],
                    resultado["Vdi"], resultado["Vqi"], resultado["theta0"],
                    resultado.get("Fsys", 0),
                ])
            except Exception as e:
                print(f"Error en t={ctx['time']:.3f}s: {e}")
                break

        header = ["Tiempo", "Pref", "Wr", "Tm", "Wg", "Iq", "Vq",
                   "Vdc", "Vdi", "Vqi", "theta0", "Fsys"]
        with open("resultados_diesel.csv", "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(header)
            writer.writerows(self.datos)


if __name__ == "__main__":
    sistema = SistemaDiesel()
    sistema.ejecutar()
