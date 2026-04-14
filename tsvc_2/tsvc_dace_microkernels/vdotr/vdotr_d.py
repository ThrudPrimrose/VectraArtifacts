import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def vdotr_d(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], dot_out: dace.float64[LEN_1D]
):
    dot_out[0] = 0.0
    for nl in range(ITERATIONS * 10):
        dot_out[0] = 0.0
        for i in range(LEN_1D):
            dot_out[0] = dot_out[0] + a[i] * b[i]

