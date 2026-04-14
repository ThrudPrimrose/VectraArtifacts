import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s274_f(
    a: dace.float32[LEN_1D],
    b: dace.float32[LEN_1D],
    c: dace.float32[LEN_1D],
    d: dace.float32[LEN_1D],
    e: dace.float32[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            a[i] = c[i] + e[i] * d[i]
            if a[i] > 0.0:
                b[i] = a[i] + b[i]
            else:
                a[i] = d[i] * e[i]

