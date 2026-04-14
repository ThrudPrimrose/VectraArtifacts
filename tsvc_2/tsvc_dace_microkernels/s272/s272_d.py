import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s272_d(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
    threshold: dace.int64,
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            if e[i] >= threshold:
                a[i] = a[i] + c[i] * d[i]
                b[i] = b[i] + c[i] * c[i]

