import csv
from Solar.SolarPanel import SolarPanel
from Solar.MPPTController import MPPTController
from Solar.BoostConverter import BoostConverter
from common.GridInverter import GridConnectedInverter
from common.Transformadas import Transformadas
from common.RedTrifasica import RedTrifasica


class SistemaSolar:
    """Sistema completo de generacion solar fotovoltaica conectado a red.

    Integra el panel fotovoltaico, control MPPT, convertidor elevador Boost,
    inversor trifasico conectado a red y el sistema de transformadas (PLL)
    para sincronizacion con la red electrica.

    Soporta agregacion de N_inv inversores en paralelo para plantas solares en Media Tension (MT).
    Impedancia equivalente de la planta: Z_eq = Z_out / N_inv + Z_trafo.
    """

    def __init__(self, N_inv=1, V_base_MT=13800.0, S_base_planta=1000000.0):
        """Inicializa todos los subsistemas y el estado interno de la simulacion.

        Parametros:
            N_inv: Numero de inversores en paralelo en la granja solar.
            V_base_MT: Tension base nominal de Media Tension [V].
            S_base_planta: Potencia base nominal de la planta solar [VA].
        """
        self.N_inv = max(1, int(N_inv))
        self.V_base_MT = float(V_base_MT)
        self.S_base_planta = float(S_base_planta)

        self.panel = SolarPanel()
        self.mppt = MPPTController()
        self.boost = BoostConverter()
        self.inversor = GridConnectedInverter(Vdcref=400, N_inv=self.N_inv)
        self.transformadas = Transformadas()
        self.red = RedTrifasica()
        # Irradiancia incidente en el plano del arreglo [W/m2]
        self.POA = 1000.0
        # Temperatura ambiente [K]
        self.Tam = 298.0
        # Diccionario de estado compartido entre subsistemas
        self.contexto = {
            "time": 0.0,          # Tiempo actual de simulacion [s]
            "V_pv": 0.0,          # Voltaje del panel [V]
            "I_pv": 7.6 * self.N_inv, # Corriente total del arreglo [A]
            "V_array": 0.0,       # Voltaje del arreglo completo [V]
            "P_array": 0.0,       # Potencia del arreglo [W]
            "V_ref": 350.0,       # Voltaje de referencia del MPPT [V] (~MPP)
            "duty_cycle": 0.125,  # D = 1 - Vref/Vdc = 1 - 350/400
            "V_dc": 400.0,        # Tension del bus de corriente continua [V]
            "I_inv": 0.0,         # Corriente del inversor [A]
            "Idi": 0.0,           # Corriente en el eje directo del inversor [A]
            "Iqi": 0.0,           # Corriente en el eje de cuadratura del inversor [A]
            "theta0": 0.0,        # Angulo de fase del PLL [rad]
            "Vdi": 110.0,         # Tension en el eje directo medida [V]
            "Vqi": 0.0,           # Tension en el eje de cuadratura medida [V]
            "Fsys": 60.0,         # Frecuencia del sistema [Hz]
            "Pw": 0.0,            # Potencia activa inyectada a la red [W]
            "Pq": 0.0,            # Potencia reactiva inyectada a la red [VAR]
            "N_inv": self.N_inv,  # Numero de inversores agregados
        }
        # Paso de integracion temporal [s]
        self.sample_time = 0.001
        # Ultimo tiempo de ejecucion del MPPT [s]
        self._ultimo_mppt = 0.0
        # Lista para almacenar los resultados de la simulacion
        self.datos = []

    def step(self, dt=0.001, V_pcc=None, setpoints=None):
        """Ejecuta un paso de integracion de todo el sistema solar.

        Parametros:
            dt: Paso de tiempo [s]
            V_pcc: Tension en el punto de acoplamiento comun (PCC) [V]
            setpoints: Diccionario opcional con consignas externas

        Retorna:
            Copia del diccionario de contexto con el estado actualizado.
        """
        ctx = self.contexto

        # Aplicar consignas externas si se proporcionan
        if setpoints:
            if "Q_ref_kvar" in setpoints:
                ctx["Pq"] = setpoints["Q_ref_kvar"] * 1000.0
            if "V_ref_mppt" in setpoints:
                ctx["V_ref"] = setpoints["V_ref_mppt"]

        # Obtener el voltaje real del arreglo desde la relacion del Boost
        V_array = ctx["V_dc"] * (1.0 - ctx["duty_cycle"])
        ctx["V_array"] = V_array

        # Corriente del panel en ese voltaje (curva I-V real)
        I_pv = self.panel.calculate_at_voltage(V_array, self.POA, self.Tam)
        ctx["I_pv"] = I_pv
        P_array = V_array * I_pv
        ctx["P_array"] = P_array

        # Actualizar la referencia de voltaje mediante el algoritmo MPPT
        # El MPPT se ejecuta cada 500 pasos (0.5s) para evitar que reaccione
        # a transitorios de Vdc no relacionados con el duty cycle
        if ctx["time"] - self._ultimo_mppt >= 0.5:
            ctx["V_ref"] = self.mppt.step(ctx["V_array"], ctx["I_pv"])
            self._ultimo_mppt = ctx["time"]

        # Calcular el ciclo de trabajo del convertidor elevador Boost
        # Feedforward: D = 1 - Vref/Vdc (relacion algebraica exacta)
        ctx["duty_cycle"] = self.boost.calculate_duty_cycle(ctx["V_ref"], ctx["V_array"], ctx["V_dc"])

        # Ejecutar un paso del inversor conectado a red
        Pw, Pq, Idi, Iqi, Vdt, Idiref = self.inversor.step(
            ctx["V_dc"], ctx["Vdi"], ctx["Vqi"], ctx["theta0"], ctx["I_pv"], dt,
            D=ctx["duty_cycle"])
        ctx["Pw"] = Pw
        ctx["Pq"] = Pq
        ctx["Idi"] = Idi
        ctx["Iqi"] = Iqi
        ctx["Idiref"] = Idiref

        # Actualizar el bus DC del convertidor Boost
        # NOTA: Idi es ahora la corriente equivalente DC que demanda el inversor (Iinv_dc)
        # Esta corriente ya incluye la relacion de transformacion Vdi/Vdc
        _, Vdc_new = self.boost.update_state(
            ctx["duty_cycle"], ctx["I_pv"], ctx["V_array"], ctx["Idi"], dt)
        ctx["V_dc"] = Vdc_new

        # Obtener la tension trifasica de la red o usar el valor externo del PCC
        if V_pcc is not None:
            Va, Vb, Vc = V_pcc, 0.0, 0.0
            ctx["V_actual"] = V_pcc
        else:
            Va, Vb, Vc = self.red.get_voltages(ctx["time"])

        # Aplicar las transformadas de Clarke y Park (PLL) para sincronizacion
        Valpha, Vbeta, theta0, Vq_out, Vd_out, Fsys = \
            self.transformadas.aplicar_transformadas([Va, Vb, Vc], ctx["Vqi"])
        ctx["theta0"] = theta0
        ctx["Vqi"] = Vq_out
        ctx["Vdi"] = Vd_out
        ctx["Fsys"] = Fsys

        ctx["time"] = round(ctx["time"] + dt, 3)
        return dict(ctx)

    def ejecutar(self, tiempo_simulacion=10):
        """Ejecuta la simulacion durante un intervalo de tiempo especificado.

        Parametros:
            tiempo_simulacion: Duracion total de la simulacion [s]
        """
        ctx = self.contexto
        while ctx["time"] < tiempo_simulacion:
            try:
                resultado = self.step(self.sample_time)
                Va, Vb, Vc = ctx["Vdi"], ctx["Vqi"], ctx["Fsys"]
                self.datos.append([
                    resultado["time"], resultado["V_pv"], resultado["I_pv"],
                    resultado["V_array"], resultado["P_array"], resultado["V_ref"],
                    resultado["duty_cycle"], resultado["V_dc"], resultado["Idi"],
                    resultado["Pw"], resultado["Pq"], resultado.get("Idiref", resultado["Idi"]), resultado["Iqi"],
                    resultado["Vdi"], resultado["Vqi"], resultado["Fsys"],
                    Va, Vb, Vc
                ])
            except Exception as e:
                print(f"Error en t={ctx['time']:.3f}s: {str(e)}")
                break
        self._guardar_csv()

    def _guardar_csv(self):
        """Guarda los resultados de la simulacion en un archivo CSV."""
        header = [
            "time", "V_pv", "I_pv", "V_array", "P_array", "V_ref",
            "duty_cycle", "V_dc", "Idi", "Pw", "Pq",
            "Idiref", "Iqi", "Vdi", "Vqi", "Fsys",
            "Va", "Vb", "Vc"
        ]
        with open("resultados_solar.csv", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(self.datos)


if __name__ == "__main__":
    sistema = SistemaSolar()
    sistema.ejecutar(tiempo_simulacion=5)
