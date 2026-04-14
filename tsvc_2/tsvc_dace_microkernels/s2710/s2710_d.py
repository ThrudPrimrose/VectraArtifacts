import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s2710_d(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
    x: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS // 2):
        for i in range(LEN_1D):
            if a[i] > b[i]:
                a[i] = a[i] + b[i] * d[i]
                if LEN_1D > 10:
                    c[i] = c[i] + d[i] * d[i]
                else:
                    c[i] = d[i] * e[i] + 1.0
            else:
                b[i] = a[i] + e[i] * e[i]
                if x[0] > 0.0:
                    c[i] = a[i] + d[i] * d[i]
                else:
                    c[i] = c[i] + e[i] * e[i]

