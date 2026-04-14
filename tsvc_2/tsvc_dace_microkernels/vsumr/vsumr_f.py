import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def vsumr_f(a: dace.float32[LEN_1D], sum_out: dace.float32[1]):
    s = 0.0
    for nl in range(ITERATIONS * 10):
        s = 0.0
        for i in range(LEN_1D):
            s = s + a[i]
    sum_out[0] = s

