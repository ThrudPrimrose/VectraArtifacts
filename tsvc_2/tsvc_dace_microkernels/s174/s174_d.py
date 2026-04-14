import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s174_d(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], M: dace.int64):
    for nl in range(10 * ITERATIONS):
        for i in range(M):
            a[i + M] = a[i] + b[i]

