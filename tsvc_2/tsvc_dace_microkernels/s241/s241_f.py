import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s241_f(
    a: dace.float32[LEN_1D],
    b: dace.float32[LEN_1D],
    c: dace.float32[LEN_1D],
    d: dace.float32[LEN_1D],
):
    outer = 2 * ITERATIONS
    for nl in range(outer):
        for i in range(LEN_1D - 1):
            a[i] = b[i] * c[i] * d[i]
            b[i] = a[i] * a[i + 1] * d[i]

