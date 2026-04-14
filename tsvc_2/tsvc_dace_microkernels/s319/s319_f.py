import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s319_f(
    a: dace.float32[LEN_1D],
    b: dace.float32[LEN_1D],
    c: dace.float32[LEN_1D],
    d: dace.float32[LEN_1D],
    e: dace.float32[LEN_1D],
):
    for nl in range(2 * ITERATIONS):
        sum_val = 0.0
        for i in range(LEN_1D):
            a[i] = c[i] + d[i]
            sum_val = sum_val + a[i]
            b[i] = c[i] + e[i]
            sum_val = sum_val + b[i]
        b[0] = sum_val

