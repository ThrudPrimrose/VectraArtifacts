import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s161_f(
    a: dace.float32[LEN_1D],
    b: dace.float32[LEN_1D],
    c: dace.float32[LEN_1D],
    d: dace.float32[LEN_1D],
    e: dace.float32[LEN_1D],
):
    for nl in range(ITERATIONS // 2):
        for i in range(LEN_1D):
            if b[i] < 0.0:
                c[i + 1] = a[i] + d[i] * d[i]
            else:
                a[i] = c[i] + d[i] * e[i]

