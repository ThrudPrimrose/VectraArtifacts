import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s152_f(
    a: dace.float32[LEN_1D],
    b: dace.float32[LEN_1D],
    c: dace.float32[LEN_1D],
    d: dace.float32[LEN_1D],
    e: dace.float32[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            b[i] = d[i] * e[i]
        for i in range(LEN_1D):
            a[i] = a[i] + b[i] * c[i]

