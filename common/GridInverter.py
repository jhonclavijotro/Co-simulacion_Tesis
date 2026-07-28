import math


class GridConnectedInverter:
    def __init__(self, fn=60, Tn=110, Vdcref=420):
        self.fn = fn
        self.Tn = Tn
        self.Vdcref = Vdcref
        self.Kp_vdc = 0.05
        self.Ki_vdc = 0.02
        self.I_int_vdc = 0.0
        self.E7 = 0.0
        self.y4 = 0.0
        self.E9 = 0.0
        self.y5 = 0.0
        self.Idi = 0.0
        self.Iqi = 0.0
        self.Idi1 = 0.0
        self.Iqi1 = 0.0
        self.I_inv_max = 50.0

    def controlvdc_PI(self, error, I_int_prev, Kp, Ki, Ts,
                      I_int_min=-5.0, I_int_max=5.0):
        u_unsat = Kp * error + I_int_prev
        if u_unsat < self.I_inv_max and u_unsat > -self.I_inv_max:
            I_int = I_int_prev + error * Ki * Ts
        else:
            I_int = I_int_prev
        I_int = max(min(I_int, I_int_max), I_int_min)
        u = Kp * error + I_int
        return max(min(u, self.I_inv_max), -self.I_inv_max), I_int

    def control3(self, E, E_prev, y_prev):
        y = 0.09 * E + 0.2 * E_prev + y_prev
        return y

    def decoupledC(self, Md, Mq, Wg, Id, Iq):
        Ls = 5e-3
        Ud = Md - (Iq * Wg * Ls)
        Uq = Mq + (Id * Wg * Ls)
        return Ud, Uq

    def inductor(self, Vtd, Vtq, VdG, VqG, wt, Idi1, Iqi1):
        Ls = 5e-3
        xd = Vtd - VdG + (Iqi1 * Ls * wt)
        Ud = (Idi1 * 0.9) + (0.2 * xd)
        xq = Vtq - VqG - (Idi1 * Ls * wt)
        Uq = (Iqi1 * 0.9) + (0.2 * xq)
        return max(min(Ud, self.I_inv_max), -self.I_inv_max), max(min(Uq, self.I_inv_max), -self.I_inv_max)

    def step(self, Vdc, Vdi, Vqi, theta, Ig, sample_time, D=0.0):
        Evdc = self.Vdcref - Vdc
        Mvdc, self.I_int_vdc = self.controlvdc_PI(
            Evdc, self.I_int_vdc, self.Kp_vdc, self.Ki_vdc, sample_time
        )
        Iboost = Ig * (1.0 - D) if D >= 0 else Ig
        P_dc = Vdc * Iboost
        vdi_clamped = max(min(Vdi, 120.0), 100.0) if abs(Vdi) > 1.0 else 110.0
        Idiref = P_dc / vdi_clamped - Mvdc
        Iqiref = 0.0

        tau = 0.5
        self.Idi = self.Idi + tau * (Idiref - self.Idi)
        self.Iqi = self.Iqi + tau * (Iqiref - self.Iqi)
        self.Idi = max(min(self.Idi, self.I_inv_max), -self.I_inv_max)
        self.Iqi = max(min(self.Iqi, self.I_inv_max), -self.I_inv_max)

        Pw = P_dc
        Pq = 0.0

        Iinv_dc = Iboost

        return Pw, Pq, Iinv_dc, self.Iqi, 0.0, Idiref
