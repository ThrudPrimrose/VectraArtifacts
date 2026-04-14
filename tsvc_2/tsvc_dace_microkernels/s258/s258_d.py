import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s258_d(
    a: dace.float64[LEN_2D],
    b: dace.float64[LEN_2D],
    c: dace.float64[LEN_2D],
    d: dace.float64[LEN_2D],
    e: dace.float64[LEN_2D],
    aa: dace.float64[1, LEN_2D],
):
    for nl in range(ITERATIONS):
        s = 0.0
        for i in range(LEN_2D):
            if a[i] > 0.0:
                s = d[i] * d[i]
            b[i] = s * c[i] + d[i]
            e[i] = (s + 1.0) * aa[0, i]

