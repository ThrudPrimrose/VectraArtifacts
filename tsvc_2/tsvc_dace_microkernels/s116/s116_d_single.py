import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s116_d_single(a: dace.float64[LEN_1D]):
    for i in range(0, LEN_1D - 4, 4):
        a[i] = a[i + 1] * a[i]
        a[i + 1] = a[i + 2] * a[i + 1]
        a[i + 2] = a[i + 3] * a[i + 2]
        a[i + 3] = a[i + 4] * a[i + 3]

