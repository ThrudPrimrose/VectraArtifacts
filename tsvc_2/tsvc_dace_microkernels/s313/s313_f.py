import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s313_f(
    a: dace.float32[LEN_1D], b: dace.float32[LEN_1D], dot: dace.float32[1]
):
    for nl in range(10 * ITERATIONS):
        dot[0] = 0.0
        for i in range(LEN_1D):
            dot[0] = dot[0] + a[i] * b[i]

