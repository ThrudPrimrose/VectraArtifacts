import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s331_d(a: dace.float64[LEN_1D], b: dace.float64[2]):
    j = -1
    for nl in range(ITERATIONS):
        j = -1
        for i in range(LEN_1D):
            if a[i] < 0.0:
                j = i
    b[0] = j

