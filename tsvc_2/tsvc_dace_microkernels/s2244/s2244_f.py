import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s2244_f(
    a: dace.float32[LEN_1D],
    b: dace.float32[LEN_1D],
    c: dace.float32[LEN_1D],
    e: dace.float32[LEN_1D],
):
    for nl in range(ITERATIONS):
        a[LEN_1D - 1] = b[LEN_1D - 2] + e[LEN_1D - 2]
        for i in range(LEN_1D - 1):
            a[i] = b[i] + c[i]

