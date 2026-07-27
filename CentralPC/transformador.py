"""Modelo de transformador trifasico para FBS usando componentes simetricas.

Soporta conexiones Dyn11, YNd, Yy0, Dd0 con desfase y bloqueo de
secuencia cero. Basado en Kersting (2002) y en el codigo de referencia
de PasanBhanu/loadflow-forward-backward-sweep.
"""

import cmath
import math

A = complex(math.cos(2*math.pi/3), math.sin(2*math.pi/3))
A2 = A * A
FORTESCUE = [[1, 1, 1], [1, A2, A], [1, A, A2]]
FORTESCUE_INV = [[1, 1, 1], [1, A, A2], [1, A2, A]]
for row in FORTESCUE_INV:
    for i in range(3):
        row[i] /= 3


def _aplicar_fortescue(abc):
    """Convierte vector abc a componentes simetricas 012."""
    inv = FORTESCUE_INV
    return [
        inv[0][0]*abc[0] + inv[0][1]*abc[1] + inv[0][2]*abc[2],
        inv[1][0]*abc[0] + inv[1][1]*abc[1] + inv[1][2]*abc[2],
        inv[2][0]*abc[0] + inv[2][1]*abc[1] + inv[2][2]*abc[2],
    ]


def _aplicar_inversa(seq):
    """Convierte componentes simetricas 012 a vector abc."""
    f = FORTESCUE
    return [
        f[0][0]*seq[0] + f[0][1]*seq[1] + f[0][2]*seq[2],
        f[1][0]*seq[0] + f[1][1]*seq[1] + f[1][2]*seq[2],
        f[2][0]*seq[0] + f[2][1]*seq[1] + f[2][2]*seq[2],
    ]


CONEXIONES = {
    "Dyn11":  {"angle": -30, "pri_delta": True,  "sec_delta": False},
    "YNd":    {"angle": +30, "pri_delta": False, "sec_delta": True},
    "Yy0":    {"angle": 0,   "pri_delta": False, "sec_delta": False},
    "Dd0":    {"angle": 0,   "pri_delta": True,  "sec_delta": True},
    "Dyn5":   {"angle": +150, "pri_delta": True, "sec_delta": False},
    "YNyn0":  {"angle": 0,   "pri_delta": False, "sec_delta": False},
}


class TransformadorTrifasico:
    """Transformador trifasico con modelo de componentes simetricas.

    Parametros:
        S_nominal: Potencia nominal [VA]
        V_pri: Tension primaria nominal [V] (linea-linea)
        V_sec: Tension secundaria nominal [V] (linea-linea)
        Z_pct: Impedancia de cortocircuito [%]
        X_R: Relacion X/R
        conexion: Tipo de conexion (Dyn11, YNd, Yy0, Dd0)
    """

    def __init__(self, S_nominal, V_pri, V_sec, Z_pct=5.75, X_R=5, conexion="Dyn11"):
        if conexion not in CONEXIONES:
            raise ValueError(f"Conexion no soportada: {conexion}")
        self.S = S_nominal
        self.V_pri = V_pri
        self.V_sec = V_sec
        self.N = V_pri / V_sec
        self.conexion = conexion
        cfg = CONEXIONES[conexion]
        self.angle = cfg["angle"]
        self.pri_delta = cfg["pri_delta"]
        self.sec_delta = cfg["sec_delta"]
        self.angle_rad = math.radians(self.angle)
        self.phase_shift = complex(math.cos(self.angle_rad), math.sin(self.angle_rad))

        Z_ohm = (Z_pct / 100.0) * (V_pri ** 2) / S_nominal
        phi = math.atan(X_R)
        self.Z = complex(Z_ohm * math.cos(phi), Z_ohm * math.sin(phi))
        self.Z_pct = Z_pct

    def backward(self, I_sec, V_sec=None):
        """Backward sweep: corrientes secundario → corriente primario.

        I_sec: lista [Ia, Ib, Ic] en el secundario [A]
        Retorna: [Ia, Ib, Ic] en el primario [A]
        """
        I_seq = _aplicar_fortescue(I_sec)

        if self.sec_delta:
            I_seq[0] = 0

        I_seq[1] /= self.phase_shift
        I_seq[2] *= self.phase_shift

        if self.pri_delta:
            I_seq[0] = 0

        I_seq[0] /= self.N
        I_seq[1] /= self.N
        I_seq[2] /= self.N

        return _aplicar_inversa(I_seq)

    def forward(self, V_pri, I_pri):
        """Forward sweep: tensiones primario → tension secundario.

        V_pri: lista [Va, Vb, Vc] en el primario [V]
        I_pri: lista [Ia, Ib, Ic] en el primario [A]
        Retorna: [Va, Vb, Vc] en el secundario [V]
        """
        V_seq = _aplicar_fortescue(V_pri)
        I_seq = _aplicar_fortescue(I_pri)

        if self.pri_delta:
            V_seq[0] = 0

        Z0 = self.Z * 0.85
        V_seq[0] -= Z0 * I_seq[0]
        V_seq[1] -= self.Z * I_seq[1]
        V_seq[2] -= self.Z * I_seq[2]

        V_seq[1] *= self.phase_shift
        V_seq[2] /= self.phase_shift

        V_seq[0] /= self.N
        V_seq[1] /= self.N
        V_seq[2] /= self.N

        if self.sec_delta:
            V_seq[0] = 0

        return _aplicar_inversa(V_seq)

    def calcular_perdidas(self, I_pri):
        """Calcula perdidas en el cobre [W]."""
        I_seq = _aplicar_fortescue(I_pri)
        return 3 * (abs(I_seq[1])**2 + abs(I_seq[2])**2) * self.Z.real

    def __str__(self):
        return (f"Transformador {self.conexion}: "
                f"{self.V_pri/1000:.1f}kV/{self.V_sec/1000:.2f}kV, "
                f"{self.S/1e6:.1f}MVA, Z={self.Z_pct:.2f}%")
