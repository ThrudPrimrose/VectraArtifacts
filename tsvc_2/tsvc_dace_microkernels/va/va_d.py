import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def va_d(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(ITERATIONS * 10):
        for i in range(LEN_1D):
            a[i] = b[i]

