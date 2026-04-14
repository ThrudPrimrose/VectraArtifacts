import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s128_f(
    a: dace.float32[LEN_1D],
    b: dace.float32[LEN_1D],
    c: dace.float32[LEN_1D],
    d: dace.float32[LEN_1D],
):
    for nl in range(2 * ITERATIONS):
        j = -1
        for i in range(LEN_1D // 2):
            k = j + 1
            a[i] = b[k] - d[i]
            j = k + 1
            b[k] = a[i] + c[k]

