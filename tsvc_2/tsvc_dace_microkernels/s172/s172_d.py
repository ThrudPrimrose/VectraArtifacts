import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s172_d(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], n1: dace.int64, n3: dace.int64
):
    for nl in range(ITERATIONS):
        for i in range(n1 - 1, LEN_1D, n3):
            a[i] = a[i] + b[i]

