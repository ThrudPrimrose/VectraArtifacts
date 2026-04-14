import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s253_d(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            if a[i] > b[i]:
                s = a[i] - b[i] * d[i]
                c[i] = c[i] + s
                a[i] = s

