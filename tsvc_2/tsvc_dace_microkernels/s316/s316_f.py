import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s316_f(a: dace.float32[LEN_1D], result: dace.float32[1]):
    for nl in range(ITERATIONS):
        x = a[0]
        for i in range(1, LEN_1D):
            if a[i] < x:
                x = a[i]
    result[0] = x

