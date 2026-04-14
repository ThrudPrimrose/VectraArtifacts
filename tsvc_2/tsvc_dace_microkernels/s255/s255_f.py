import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s255_f(a: dace.float32[LEN_1D], b: dace.float32[LEN_1D]):
    for nl in range(ITERATIONS):
        x = b[LEN_1D - 1]
        y = b[LEN_1D - 2]
        for i in range(LEN_1D):
            a[i] = (b[i] + x + y) * 0.333
            y = x
            x = b[i]

