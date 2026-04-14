import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")
S = dace.symbol('S')

@dace.program
def vpvts_d(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            a[i] = a[i] + b[i] * S

