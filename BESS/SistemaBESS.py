import csv
import numpy as np
from BESS.Bateria import Bateria
from BESS.BuckBoost import BuckBoost
from common.GridInverter import GridConnectedInverter
from common.Transformadas import Transformadas


class SistemaBESS:
    """Sistema completo de almacenamiento BESS conectado a red.

    Dos modos de operacion:
      modo="detallado": Usa GridInverter + PLL (para estudios EMT con
                        paso fino, < 50 us). NO apto para co-simulacion
                        con paso 0.1s.
      modo="promedio":  Modelo promedio que sigue P_ref directamente.
                        Apto para integracion MAS con paso 0.1s.

    En modo promedio, el inversor se modela como:
      P_inv = P_ref
      I_inv = P_ref / Vdc (para balance de potencia en bus DC)
    """

    def __init__(self, V_nominal=48.0, capacidad_Ah=200.0, SoC_inicial=0.5,
                 N_serie=10, N_paralelo=1, Vdcref=400, V_rms=110.0,
                 modo="promedio", I_inv_max=50.0):
        self.modo = modo
        self.bateria = Bateria(
            V_nominal=V_nominal, capacidad_Ah=capacidad_Ah,
            SoC_inicial=SoC_inicial, N_serie=N_serie,
            N_paralelo=N_paralelo
        )
        self.buck_boost = BuckBoost()
        self.Vdcref = Vdcref

        if modo == "detallado":
            self.inversor = GridConnectedInverter(Vdcref=Vdcref)
            self.transformadas = Transformadas()
        else:
            self.inversor = None
            self.transformadas = None

        self.V_rms = V_rms
        self.V_pu_base = V_rms
        self.I_inv_max = I_inv_max
        self._lvrt_active = False
        self.sample_time = 0.001
        self.theta_grid = 0.0
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
            "P_ref_orig": 0.0,
            "V_dc": Vdcref,
            "duty": 0.0,
            "Idi": 0.0,
            "Iqi": 0.0,
            "theta0": 0.0,
            "Vdi": self.V_rms,
            "Vqi": 0.0,
            "Fsys": 60.0,
            "Pw": 0.0,
            "Pq": 0.0,
            "P_inv_ac": 0.0,
            "V_pcc_pu": 1.0,
            "lvrt_scaling": 1.0,
        }

    def _gen_3ph(self, theta, v_rms):
        Vpk = v_rms * math.sqrt(2.0)
        Va = Vpk * math.cos(theta)
        Vb = Vpk * math.cos(theta - 2.09439510239)
        Vc = Vpk * math.cos(theta + 2.09439510239)
        return Va, Vb, Vc

    def _lvrt_factor(self, V_pcc_pu):
        if V_pcc_pu >= 0.88:
            return 1.0
        elif V_pcc_pu >= 0.50:
            return 0.88 * (V_pcc_pu - 0.50) / (0.88 - 0.50)
        else:
            return 0.0

    def _paso_interno_promedio(self, dt, V_pcc, P_ref, Q_ref):
        ctx = self.contexto
        ctx["P_ref_orig"] = P_ref

        if V_pcc is not None:
            V_pcc_pu = abs(V_pcc) / self.V_pu_base if self.V_pu_base > 0 else 1.0
        else:
            V_pcc_pu = 1.0
        ctx["V_pcc_pu"] = V_pcc_pu

        lvrt_s = self._lvrt_factor(V_pcc_pu)
        ctx["lvrt_scaling"] = lvrt_s
        P_ref_eff = P_ref * lvrt_s
        ctx["P_ref"] = P_ref_eff

        V_bat = self.bateria.calcular_V(ctx["I_bat"])
        ctx["V_bat"] = V_bat
        ctx["V_oc"] = self.bateria.V_oc

        I_bat_ref = self.buck_boost.calcular_referencia_corriente(P_ref_eff, V_bat)
        duty = self.buck_boost.control_corriente(I_bat_ref, ctx["I_bat"], dt)
        ctx["duty"] = duty

        I_inv = P_ref_eff / max(ctx["V_dc"], 1.0)
        I_inv = max(-self.I_inv_max, min(self.I_inv_max, I_inv))
        I_bat, Vdc = self.buck_boost.actualizar_estado(
            duty, I_bat_ref, V_bat, ctx["V_dc"], I_inv, dt
        )
        ctx["I_bat"] = I_bat
        ctx["V_dc"] = Vdc

        self.bateria.actualizar_SoC(I_bat, dt)
        ctx["SoC"] = self.bateria.SoC
        ctx["P_bat"] = V_bat * I_bat
        ctx["Pw"] = P_ref_eff

        ctx["time"] = round(ctx["time"] + dt, 3)

    def _paso_interno_detallado(self, dt, V_pcc, P_ref, Q_ref):
        ctx = self.contexto
        ctx["P_ref"] = P_ref

        V_bat = self.bateria.calcular_V(ctx["I_bat"])
        ctx["V_bat"] = V_bat
        ctx["V_oc"] = self.bateria.V_oc

        I_bat_ref = self.buck_boost.calcular_referencia_corriente(P_ref, V_bat)
        duty = self.buck_boost.control_corriente(I_bat_ref, ctx["I_bat"], dt)
        ctx["duty"] = duty

        I_inv = ctx.get("P_inv_ac", 0.0) / max(ctx["V_dc"], 1.0)
        I_bat, Vdc = self.buck_boost.actualizar_estado(
            duty, I_bat_ref, V_bat, ctx["V_dc"], I_inv, dt
        )
        ctx["I_bat"] = I_bat
        ctx["V_dc"] = Vdc

        self.bateria.actualizar_SoC(I_bat, dt)
        ctx["SoC"] = self.bateria.SoC
        ctx["P_bat"] = V_bat * I_bat

        self.theta_grid += 2.0 * np.pi * 60.0 * dt
        if self.theta_grid > 2.0 * np.pi:
            self.theta_grid -= 2.0 * np.pi
        v_rms = self.V_rms if V_pcc is None else abs(V_pcc)
        Va, Vb, Vc = self._gen_3ph(self.theta_grid, v_rms)

        Pw, Pq, Idi, Iqi, Vdt, Idiref = self.inversor.step(
            ctx["V_dc"], ctx["Vdi"], ctx["Vqi"], ctx["theta0"],
            ctx["Idi"], dt
        )
        ctx["Pw"] = Pw
        ctx["Pq"] = Pq
        ctx["Idi"] = Idi
        ctx["Iqi"] = Iqi
        ctx["P_inv_ac"] = Pw

        _, _, theta0, Vq_out, Vd_out, Fsys = \
            self.transformadas.aplicar_transformadas([Va, Vb, Vc],
                                                      ctx["Vqi"])
        ctx["theta0"] = theta0
        ctx["Vqi"] = Vq_out
        ctx["Vdi"] = Vd_out
        ctx["Fsys"] = Fsys

        ctx["time"] = round(ctx["time"] + dt, 3)

    def step(self, dt=0.001, V_pcc=None, setpoints=None):
        P_ref = 0.0
        Q_ref = 0.0
        if setpoints:
            if "P_ref_w" in setpoints:
                P_ref = setpoints["P_ref_w"]
            if "Q_ref_kvar" in setpoints:
                Q_ref = setpoints["Q_ref_kvar"]

        paso = (self._paso_interno_detallado if self.modo == "detallado"
                else self._paso_interno_promedio)

        if dt <= self.sample_time:
            paso(dt, V_pcc, P_ref, Q_ref)
        else:
            n = max(1, round(dt / self.sample_time))
            dt_int = dt / n
            for _ in range(n):
                paso(dt_int, V_pcc, P_ref, Q_ref)

        return dict(self.contexto)

    def ejecutar(self, tiempo_simulacion=10):
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
                    resultado["V_pcc_pu"], resultado["lvrt_scaling"],
                ])
            except Exception as e:
                print(f"Error en t={ctx['time']:.3f}s: {e}")
                break

        header = [
            "time", "SoC", "V_bat", "I_bat", "P_bat", "P_ref",
            "V_dc", "duty", "Pw", "V_pcc_pu", "lvrt_scaling"
        ]
        with open("resultados_bess.csv", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(self.datos)

        print("Simulacion BESS finalizada. Datos guardados en resultados_bess.csv")


if __name__ == "__main__":
    sistema = SistemaBESS(SoC_inicial=0.8, modo="promedio")
    sistema.ejecutar(tiempo_simulacion=10)
