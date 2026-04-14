import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s313_d_single(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], dot: dace.float64[1]
):
    dot[0] = 0.0
    for i in range(LEN_1D):
        dot[0] = dot[0] + a[i] * b[i]

