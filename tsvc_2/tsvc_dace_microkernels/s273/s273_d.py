import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s273_d(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            a[i] = a[i] + d[i] * e[i]
            if a[i] < 0.0:
                b[i] = b[i] + d[i] * e[i]
            c[i] = c[i] + a[i] * d[i]

