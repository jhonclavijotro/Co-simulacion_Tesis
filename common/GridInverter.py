import math


class GridConnectedInverter:
    def __init__(self, fn=60, Tn=110, Vdcref=420):
        self.fn = fn
        self.Tn = Tn
        self.Vdcref = Vdcref
        self.Kp_vdc = 0.008
        self.Ki_vdc = 0.016
        self.I_int_vdc = 0.0
        self.E7 = 0.0
        self.y4 = 0.0
        self.E9 = 0.0
        self.y5 = 0.0
        self.Idi = 0.0
        self.Iqi = 0.0
        self.Idi1 = 0.0
        self.Iqi1 = 0.0

    def controlvdc_PI(self, error, I_int_prev, Kp, Ki, Ts,
                      I_int_min=-10.0, I_int_max=10.0):
        I_int = I_int_prev + error * Ts
        I_int = max(min(I_int, I_int_max), I_int_min)
        u = Kp * error + Ki * I_int
        return u, I_int

    def control3(self, E, E_prev, y_prev):
        return 0.09 * E + 0.2 * E_prev + y_prev

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
        return Ud, Uq

    def step(self, Vdc, Vdi, Vqi, theta, Iqg, sample_time):
        Evdc = self.Vdcref - Vdc
        Mvdc, self.I_int_vdc = self.controlvdc_PI(
            Evdc, self.I_int_vdc, self.Kp_vdc, self.Ki_vdc, sample_time
        )
        Idiref = Iqg - Mvdc
        Iqiref = 0.0

        E6 = Idiref - self.Idi
        Mdi = self.control3(E6, self.E7, self.y4)
        self.E7, self.y4 = E6, Mdi

        E8 = Iqiref - self.Iqi
        Mqi = self.control3(E8, self.E9, self.y5)
        self.E9, self.y5 = E8, Mqi

        Vdt, Vqt = self.decoupledC(Mdi, Mqi, theta, self.Idi, self.Iqi)

        Idi_new, Iqi_new = self.inductor(Vdt, Vqt, Vdi, Vqi, theta,
                                         self.Idi1, self.Iqi1)
        self.Idi = Idi_new
        self.Iqi = Iqi_new
        self.Idi1 = Idi_new
        self.Iqi1 = Iqi_new

        Pw = (self.Idi * Vdi) + (self.Iqi * Vqi)
        Pq = (self.Idi * Vqi) - (Vdi * self.Iqi)

        return Pw, Pq, self.Idi, self.Iqi, Vdt, Idiref
