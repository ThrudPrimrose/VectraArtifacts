import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s342_d_single(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    j = -1
    for i in range(LEN_1D):
        if a[i] > 0.0:
            j = j + 1
            a[i] = b[j]

