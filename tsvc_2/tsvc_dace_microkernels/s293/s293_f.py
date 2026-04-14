import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s293_f(a: dace.float32[LEN_1D]):
    a0 = a[0]
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D):
            a[i] = a0

