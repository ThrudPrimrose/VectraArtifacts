import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s271_f(
    a: dace.float32[LEN_1D], b: dace.float32[LEN_1D], c: dace.float32[LEN_1D]
):
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D):
            if b[i] > 0.0:
                a[i] = a[i] + b[i] * c[i]

