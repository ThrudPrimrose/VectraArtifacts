import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s279_d(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS // 2):
        for i in range(LEN_1D):
            if a[i] > 0.0:
                c[i] = -c[i] + e[i] * e[i]
            else:
                b[i] = -b[i] + d[i] * d[i]
                if b[i] > a[i]:
                    c[i] = c[i] + d[i] * e[i]
            a[i] = b[i] + c[i] * d[i]

