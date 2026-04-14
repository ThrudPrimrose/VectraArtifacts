import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s351_d(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], c: dace.float64[LEN_1D]
):
    alpha = c[0]
    for nl in range(8 * ITERATIONS):
        for i in range(0, LEN_1D, 4):
            a[i] = a[i] + alpha * b[i]
            a[i + 1] = a[i + 1] + alpha * b[i + 1]
            a[i + 2] = a[i + 2] + alpha * b[i + 2]
            a[i + 3] = a[i + 3] + alpha * b[i + 3]

