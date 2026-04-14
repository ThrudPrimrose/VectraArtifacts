import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s1221_d_single(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for i in range(4, LEN_1D):
        b[i] = b[i - 4] + a[i]

