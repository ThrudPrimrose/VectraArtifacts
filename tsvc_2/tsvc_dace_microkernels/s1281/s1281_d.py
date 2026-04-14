import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s1281_d(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D):
            x = (b[i] * c[i]) + (a[i] * d[i]) + e[i]
            a[i] = x - 1.0
            b[i] = x

