import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s1213_d(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(1, LEN_1D - 1):
            a[i] = b[i - 1] + c[i]
            b[i] = a[i + 1] * d[i]

