import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s176_d(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], c: dace.float64[LEN_1D]
):
    m = LEN_1D // 2
    outer = 4 * (ITERATIONS // LEN_1D)
    for nl in range(outer):
        for j in range(LEN_1D // 2):
            for i in range(m):
                a[i] = a[i] + b[i + m - j - 1] * c[j]

