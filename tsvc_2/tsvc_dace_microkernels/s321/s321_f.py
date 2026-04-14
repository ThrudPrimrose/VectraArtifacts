import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s321_f(a: dace.float32[LEN_1D], b: dace.float32[LEN_1D]):
    for nl in range(ITERATIONS):
        for i in range(1, LEN_1D):
            a[i] = a[i] + a[i - 1] * b[i]

