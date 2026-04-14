import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s121_f(a: dace.float32[LEN_1D], b: dace.float32[LEN_1D]):
    for nl in range(3 * ITERATIONS):
        for i in range(LEN_1D - 1):
            j = i + 1
            a[i] = a[j] + b[i]

