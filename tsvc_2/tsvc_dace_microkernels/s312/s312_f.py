import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s312_f(a: dace.float32[LEN_1D], result: dace.float32[1]):
    for nl in range(10 * ITERATIONS):
        prod = 1.0
        for i in range(LEN_1D):
            prod = prod * a[i]
    result[0] = prod

