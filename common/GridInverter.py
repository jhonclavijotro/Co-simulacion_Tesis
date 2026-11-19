import math


class GridConnectedInverter:
    """Inversor Trifásico Conectado a Red en marco síncrono dq con filtro RL dinámico,
    regulación energética de bus DC, impedancia equivalente Z_eq y círculo de capacidad S_max.

    Ecuaciones del filtro RL en coordenadas síncronas dq (TEORIA.tex:34-37):
        L_f * di_d/dt = v_{i,d} - v_{g,d} - R_f * i_d + omega * L_f * i_q
        L_f * di_q/dt = v_{i,q} - v_{g,q} - R_f * i_q - omega * L_f * i_d

    Integración mediante regla trapezoidal implícita (A-estable para h = 1 ms),
    con control PI de corriente desacoplado (polo-cero, tau_i = 2 ms) y saturación
    por círculo de capacidad aparente P^2 + Q^2 <= S_max_total^2.
    """

    def __init__(
        self,
        Vdcref=400.0,
        N_inv=1,
        S_inv_nom=100000.0,
        R_out_unit=0.02,
        X_out_unit=0.10,
        R_trafo=0.01,
        X_trafo=0.05,
        omega_nom=2.0 * math.pi * 60.0,
        tau_i=0.002,
        C_dc=1000e-6,
        V_dc_min=370.0,
        V_dc_max=500.0,
        K_vdc_unit=20.0,
        bidirectional=False,
    ):
        self.Vdcref = float(Vdcref)
        self.N_inv = max(1, int(N_inv))
        self.S_inv_nom = float(S_inv_nom)
        self.R_out_unit = float(R_out_unit)
        self.X_out_unit = float(X_out_unit)
        self.R_trafo = float(R_trafo)
        self.X_trafo = float(X_trafo)

        self.omega_nom = float(omega_nom)
        self.tau_i = max(1e-4, float(tau_i))
        self.C_dc = max(1e-6, float(C_dc))
        self.V_dc_min = float(V_dc_min)
        self.V_dc_max = float(V_dc_max)
        self.K_vdc_unit = float(K_vdc_unit)
        self.bidirectional = bool(bidirectional)

        # Estados de referencia unitaria (retrocompatibles)
        self.Idi_ref = 0.0
        self.Iqi_ref = 0.0

        # Estados dinámicos del filtro RL en marco dq y del controlador PI de corriente
        self.i_d = 0.0
        self.i_q = 0.0
        self.x_id = 0.0
        self.x_iq = 0.0
        self.v_id_prev = None
        self.v_iq_prev = None
        self.last_I_dc_out = 0.0
        self.last_balance = {}

    @property
    def S_max_total(self):
        """Potencia aparente nominal agregada de la planta [VA]."""
        return self.N_inv * self.S_inv_nom

    @property
    def R_eq(self):
        """Resistencia equivalente vista desde el punto de acoplamiento [Ohm]."""
        return (self.R_out_unit / self.N_inv) + self.R_trafo

    @property
    def X_eq(self):
        """Reactancia equivalente vista desde el punto de acoplamiento [Ohm]."""
        return (self.X_out_unit / self.N_inv) + self.X_trafo

    @property
    def Z_eq(self):
        """Impedancia compleja equivalente vista desde el punto de acoplamiento [Ohm]."""
        return complex(self.R_eq, self.X_eq)

    @property
    def L_eq(self):
        """Inductancia equivalente del filtro RL + transformador [H]."""
        return self.X_eq / max(self.omega_nom, 1.0)

    @property
    def tau_rl(self):
        """Constante de tiempo electromagnética L_eq / R_eq del filtro RL [s]."""
        return self.L_eq / max(self.R_eq, 1e-9)

    def _trapezoidal_pi_axis(self, i_curr, x_curr, i_star, R_f, L_f, K_p, K_i, dt):
        """Resuelve un paso trapezoidal implícito para un eje desacoplado RL + PI."""
        dI_k = (-(R_f + K_p) * i_curr + x_curr + K_p * i_star) / L_f
        dx_k = K_i * (i_star - i_curr)
        h = 0.5 * dt
        denom = 1.0 + h * (R_f + K_p) / L_f + (h * h) * K_i / L_f
        num = i_curr + h * dI_k + (h / L_f) * (K_p * i_star + x_curr + h * (dx_k + K_i * i_star))
        i_next = num / denom
        x_next = x_curr + h * (dx_k + K_i * (i_star - i_next))
        return i_next, x_next

    def step(self, V_dc, Vdi, Vqi, theta0, I_dc_in, dt, Q_ref=0.0, **kwargs):
        dt_s = max(1e-6, float(dt))
        v_dc = max(10.0, float(V_dc))
        v_gd = float(Vdi)
        v_gq = float(Vqi)

        # 1. Potencia disponible en bus DC y cota energética física del capacitor C_dc
        p_dc_in_arg = kwargs.get("P_dc_in", None)
        if p_dc_in_arg is not None:
            P_dc_in = float(p_dc_in_arg)
            if not self.bidirectional:
                P_dc_in = max(0.0, P_dc_in)
        else:
            raw_i_dc = float(I_dc_in) if self.bidirectional else max(0.0, float(I_dc_in))
            P_dc_in = v_dc * raw_i_dc * self.N_inv

        P_vdc_reg = self.K_vdc_unit * self.N_inv * (v_dc - self.Vdcref)
        P_bridge_des = P_dc_in + P_vdc_reg

        cap_total = self.N_inv * self.C_dc
        p_cap_max_disch = 0.5 * cap_total * max(0.0, v_dc * v_dc - self.V_dc_min * self.V_dc_min) / dt_s
        p_cap_max_chg = 0.5 * cap_total * max(0.0, self.V_dc_max * self.V_dc_max - v_dc * v_dc) / dt_s
        P_dc_avail_max = P_dc_in + p_cap_max_disch
        P_dc_avail_min = P_dc_in - p_cap_max_chg

        P_bridge_ref = max(P_dc_avail_min, min(P_dc_avail_max, P_bridge_des))
        if not self.bidirectional:
            P_bridge_ref = max(0.0, P_bridge_ref)

        # 2. Compensación de pérdidas óhmicas y círculo de capacidad aparente S_max^2 >= P^2 + Q^2
        R_f = self.R_eq
        L_f = self.L_eq
        omega = self.omega_nom
        P_loss_est = 1.5 * R_f * (self.i_d * self.i_d + self.i_q * self.i_q)
        P_ac_ref = P_bridge_ref - P_loss_est
        if not self.bidirectional:
            P_ac_ref = max(0.0, P_ac_ref)

        S_max = self.S_max_total
        P_lim = max(-S_max, min(S_max, P_ac_ref))
        Q_avail = math.sqrt(max(0.0, S_max * S_max - P_lim * P_lim))
        q_req = float(Q_ref)
        Q_lim = max(-Q_avail, min(Q_avail, q_req))
        s_limited = (abs(P_lim - P_ac_ref) > 1e-6) or (abs(Q_lim - q_req) > 1e-6)

        v_sq = max(v_gd * v_gd + v_gq * v_gq, 1.0)
        Id_ref = (P_lim * v_gd + Q_lim * v_gq) / (1.5 * v_sq)
        Iq_ref = (P_lim * v_gq - Q_lim * v_gd) / (1.5 * v_sq)

        # 3. Filtro RL en marco dq (TEORIA.tex:35-36) integrado por regla trapezoidal implícita
        K_p = L_f / self.tau_i
        K_i = R_f / self.tau_i

        I_d_next, x_id_next = self._trapezoidal_pi_axis(self.i_d, self.x_id, Id_ref, R_f, L_f, K_p, K_i, dt_s)
        I_q_next, x_iq_next = self._trapezoidal_pi_axis(self.i_q, self.x_iq, Iq_ref, R_f, L_f, K_p, K_i, dt_s)

        v_id = v_gd - omega * L_f * I_q_next + K_p * (Id_ref - I_d_next) + x_id_next
        v_iq = v_gq + omega * L_f * I_d_next + K_p * (Iq_ref - I_q_next) + x_iq_next

        # Límite físico de modulación escalado por V_dc actual
        v_g_mag = math.hypot(v_gd, v_gq)
        v_inv_max = max(v_dc / math.sqrt(3.0), 1.25 * v_g_mag) * (max(v_dc, 100.0) / self.Vdcref)
        v_mag = math.hypot(v_id, v_iq)
        if v_mag > v_inv_max and v_mag > 1e-6:
            scale_v = v_inv_max / v_mag
            v_id *= scale_v
            v_iq *= scale_v
            v_id_k = v_id if self.v_id_prev is None else self.v_id_prev
            v_iq_k = v_iq if self.v_iq_prev is None else self.v_iq_prev
            di_d_k = (v_id_k - v_gd - R_f * self.i_d + omega * L_f * self.i_q) / L_f
            di_q_k = (v_iq_k - v_gq - R_f * self.i_q - omega * L_f * self.i_d) / L_f
            h = 0.5 * dt_s
            rhs_d = self.i_d + (h / L_f) * (v_id - v_gd) + h * di_d_k
            rhs_q = self.i_q + (h / L_f) * (v_iq - v_gq) + h * di_q_k
            a = 1.0 + h * R_f / L_f
            b = h * omega
            det = a * a + b * b
            I_d_next = (a * rhs_d + b * rhs_q) / det
            I_q_next = (-b * rhs_d + a * rhs_q) / det
            # Anti-windup: retener integradores de corriente cuando satura el puente
            x_id_next = self.x_id
            x_iq_next = self.x_iq

        # 4. Potencias AC efectivas en PCC y balance energético exacto en el puente
        Pw = 1.5 * (v_gd * I_d_next + v_gq * I_q_next)
        Pq = 1.5 * (v_gq * I_d_next - v_gd * I_q_next)
        P_loss_rl = 1.5 * R_f * (I_d_next * I_d_next + I_q_next * I_q_next)
        P_stored_l = 0.75 * L_f * (
            (I_d_next * I_d_next + I_q_next * I_q_next) - (self.i_d * self.i_d + self.i_q * self.i_q)
        ) / dt_s
        P_bridge = Pw + P_loss_rl + P_stored_l

        self.last_I_dc_out = P_bridge / (v_dc * self.N_inv)
        self.i_d = I_d_next
        self.i_q = I_q_next
        self.x_id = x_id_next
        self.x_iq = x_iq_next
        self.v_id_prev = v_id
        self.v_iq_prev = v_iq
        self.Idi_ref = Id_ref / self.N_inv
        self.Iqi_ref = Iq_ref / self.N_inv

        S_actual = math.hypot(Pw, Pq)
        Vdt = math.hypot(v_id, v_iq)

        self.last_balance = {
            "P_dc_in": P_dc_in,
            "P_bridge": P_bridge,
            "P_ac_out": Pw,
            "Q_ac_out": Pq,
            "P_loss_rl": P_loss_rl,
            "P_stored_l": P_stored_l,
            "I_dc_out": self.last_I_dc_out,
            "S_actual": S_actual,
            "S_max_total": S_max,
            "s_limited": s_limited,
            "tau_rl": self.tau_rl,
            "tau_i": self.tau_i,
            "R_eq": R_f,
            "X_eq": self.X_eq,
        }

        return Pw, Pq, I_d_next, I_q_next, Vdt, Id_ref
