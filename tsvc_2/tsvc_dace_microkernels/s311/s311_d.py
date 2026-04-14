import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s311_d(a: dace.float64[LEN_1D], sum_out: dace.float64[LEN_1D]):
    for nl in range(ITERATIONS * 10):
        sum_out[0] = 0.0
        for i in range(LEN_1D):
            sum_out[0] = sum_out[0] + a[i]

