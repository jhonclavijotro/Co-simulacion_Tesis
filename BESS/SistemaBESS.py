import csv
from BESS.Bateria import Bateria
from BESS.BuckBoost import BuckBoost
from common.GridInverter import GridConnectedInverter
from common.Transformadas import Transformadas


class SistemaBESS:
    """Sistema completo de almacenamiento BESS conectado a red.

    Integra el modelo de bateria de ion-litio, convertidor DC-DC
    bidireccional, inversor trifasico conectado a red y PLL para
    sincronizacion con la red electrica.

    El sistema acepta consignas de potencia (P_ref, Q_ref) desde
    el agente de consenso MAS para participar en el control
    secundario de tension y frecuencia.
    """

    def __init__(self, V_nominal=48.0, capacidad_Ah=200.0, SoC_inicial=0.5,
                 N_serie=10, N_paralelo=1, Vdcref=400):
        self.bateria = Bateria(
            V_nominal=V_nominal, capacidad_Ah=capacidad_Ah,
            SoC_inicial=SoC_inicial, N_serie=N_serie,
            N_paralelo=N_paralelo
        )
        self.buck_boost = BuckBoost()
        self.inversor = GridConnectedInverter(Vdcref=Vdcref)
        self.transformadas = Transformadas()

        self.sample_time = 0.001
        self.datos = []

        V_pack = self.bateria.V_nominal_pack

        self.contexto = {
            "time": 0.0,
            "SoC": SoC_inicial,
            "V_bat": V_pack,
            "I_bat": 0.0,
            "V_oc": V_pack,
            "P_bat": 0.0,
            "P_ref": 0.0,
            "V_dc": Vdcref,
            "duty": 0.0,
            "Idi": 0.0,
            "Iqi": 0.0,
            "theta0": 0.0,
            "Vdi": 110.0,
            "Vqi": 0.0,
            "Fsys": 60.0,
            "Pw": 0.0,
            "Pq": 0.0,
        }

    def step(self, dt=0.001, V_pcc=None, setpoints=None):
        """Ejecuta un paso de integracion del sistema BESS.

        Parametros:
            dt: Paso de tiempo [s]
            V_pcc: Tension en el punto de acoplamiento comun [V]
            setpoints: Diccionario con consignas externas
                       (P_ref_w, Q_ref_kvar)

        Retorna:
            Copia del diccionario de contexto con el estado actualizado.
        """
        ctx = self.contexto

        P_ref = 0.0
        if setpoints:
            if "P_ref_w" in setpoints:
                P_ref = setpoints["P_ref_w"]
            if "Q_ref_kvar" in setpoints:
                ctx["Pq"] = setpoints["Q_ref_kvar"] * 1000.0
        ctx["P_ref"] = P_ref

        V_bat = self.bateria.calcular_V(ctx["I_bat"])
        ctx["V_bat"] = V_bat
        ctx["V_oc"] = self.bateria.V_oc

        I_bat_ref = self.buck_boost.calcular_referencia_corriente(P_ref, V_bat)
        duty = self.buck_boost.control_corriente(I_bat_ref, ctx["I_bat"])
        ctx["duty"] = duty

        I_bat, Vdc = self.buck_boost.actualizar_estado(
            duty, I_bat_ref, V_bat, ctx["V_dc"], ctx["Idi"], dt
        )
        ctx["I_bat"] = I_bat
        ctx["V_dc"] = Vdc

        self.bateria.actualizar_SoC(I_bat, dt)
        ctx["SoC"] = self.bateria.SoC
        ctx["P_bat"] = V_bat * I_bat

        Pw, Pq, Idi, Iqi, Vdt, Idiref = self.inversor.step(
            ctx["V_dc"], ctx["Vdi"], ctx["Vqi"], ctx["theta0"],
            ctx["Idi"], dt
        )
        ctx["Pw"] = Pw
        ctx["Pq"] = Pq
        ctx["Idi"] = Idi
        ctx["Iqi"] = Iqi

        Va, Vb, Vc = 110.0, 0.0, 0.0
        if V_pcc is not None:
            Va, Vb, Vc = V_pcc, 0.0, 0.0

        _, _, theta0, Vq_out, Vd_out, Fsys = \
            self.transformadas.aplicar_transformadas([Va, Vb, Vc], ctx["Vqi"])
        ctx["theta0"] = theta0
        ctx["Vqi"] = Vq_out
        ctx["Vdi"] = Vd_out
        ctx["Fsys"] = Fsys

        ctx["time"] = round(ctx["time"] + dt, 3)
        return dict(ctx)

    def ejecutar(self, tiempo_simulacion=10):
        """Ejecuta la simulacion durante un intervalo de tiempo.

        Para propositos de prueba, genera un perfil escalon de P_ref
        que alterna carga y descarga.
        """
        ctx = self.contexto
        while ctx["time"] < tiempo_simulacion:
            try:
                t = ctx["time"]
                if t < 2.0:
                    P_ref = 0.0
                elif t < 5.0:
                    P_ref = 5000.0
                elif t < 8.0:
                    P_ref = -3000.0
                else:
                    P_ref = 0.0

                resultado = self.step(
                    self.sample_time,
                    setpoints={"P_ref_w": P_ref, "Q_ref_kvar": 0.0}
                )
                self.datos.append([
                    resultado["time"], resultado["SoC"], resultado["V_bat"],
                    resultado["I_bat"], resultado["P_bat"], resultado["P_ref"],
                    resultado["V_dc"], resultado["duty"], resultado["Pw"],
                    resultado["Pq"], resultado["Idi"], resultado["Iqi"],
                ])
            except Exception as e:
                print(f"Error en t={ctx['time']:.3f}s: {e}")
                break

        header = [
            "time", "SoC", "V_bat", "I_bat", "P_bat", "P_ref",
            "V_dc", "duty", "Pw", "Pq", "Idi", "Iqi"
        ]
        with open("resultados_bess.csv", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(self.datos)

        print("Simulacion BESS finalizada. Datos guardados en resultados_bess.csv")


if __name__ == "__main__":
    sistema = SistemaBESS(SoC_inicial=0.8)
    sistema.ejecutar(tiempo_simulacion=10)
