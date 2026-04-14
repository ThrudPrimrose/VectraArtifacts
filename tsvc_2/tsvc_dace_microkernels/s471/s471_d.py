import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s471_d(
    x: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS // 2):
        for i in range(LEN_1D):
            x[i] = b[i] + d[i] * d[i]
            b[i] = c[i] + d[i] * e[i]

