import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s175_d(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], inc: dace.int64):
    for nl in range(ITERATIONS):
        for i in range(0, LEN_1D - inc, inc):
            a[i] = a[i + inc] + b[i]

