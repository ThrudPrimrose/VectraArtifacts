import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s277_d(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D - 1):
            if a[i] < 0.0:
                if b[i] < 0.0:
                    a[i] = a[i] + c[i] * d[i]
                b[i + 1] = c[i] + d[i] * e[i]

