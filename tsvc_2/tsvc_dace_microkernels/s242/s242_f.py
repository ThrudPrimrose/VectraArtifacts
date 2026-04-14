import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s242_f(
    a: dace.float32[LEN_1D],
    b: dace.float32[LEN_1D],
    c: dace.float32[LEN_1D],
    d: dace.float32[LEN_1D],
):
    outer = ITERATIONS // 5
    for nl in range(outer):
        for i in range(1, LEN_1D):
            a[i] = a[i - 1] + 0.5 + 1.0 + b[i] + c[i] + d[i]

