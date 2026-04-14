import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def vsumr_d_single(a: dace.float64[LEN_1D], sum_out: dace.float64[1]):
    s = 0.0
    s = 0.0
    for i in range(LEN_1D):
        s = s + a[i]
    sum_out[0] = s

