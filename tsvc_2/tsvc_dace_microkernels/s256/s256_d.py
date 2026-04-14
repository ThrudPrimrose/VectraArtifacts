import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s256_d(
    a: dace.float64[LEN_2D],
    aa: dace.float64[LEN_2D, LEN_2D],
    bb: dace.float64[LEN_2D, LEN_2D],
    d: dace.float64[LEN_2D],
):
    outer = 10 * (ITERATIONS // LEN_2D)
    for nl in range(outer):
        for i in range(LEN_2D):
            for j in range(1, LEN_2D):
                a[j] = 1.0 - a[j - 1]
                aa[j, i] = a[j] + bb[j, i] * d[j]

