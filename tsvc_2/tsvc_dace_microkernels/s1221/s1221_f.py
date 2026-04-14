import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s1221_f(a: dace.float32[LEN_1D], b: dace.float32[LEN_1D]):
    for nl in range(ITERATIONS):
        for i in range(4, LEN_1D):
            b[i] = b[i - 4] + a[i]

