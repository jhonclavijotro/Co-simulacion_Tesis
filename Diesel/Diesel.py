from scipy import signal 
import numpy as np
import math

def controlDiesel(E, E1, y1):
    """
    Control proporcional-integral para el motor Diesel.
    """
    y = 0.000974170175365822 * E + 0.000691535501608831 * E1 + y1   
    if y > 10:
        return 10
    elif y < -10:
        return -10
    else:
        return y

def modeloDiesel(F, tv):
    """
    Modelo dinámico del motor Diesel.
    Retorna la respuesta (por ejemplo, torque) como una función discreta.
    """
    Ke = 1.0
    te = 0.035
    A = -1.0 / te
    B = (Ke / te) * F
    C = 1.0
    D = 0.0
    sys2 = signal.StateSpace([A], [B], [C], [D])
    sys_disc = sys2.to_discrete(0.001)
    t_out, y_out = signal.dstep(sys_disc, t=tv)
    return np.squeeze(y_out[0])
