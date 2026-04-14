import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s31111_f(a: dace.float32[LEN_1D], b: dace.float32[2]):
    for nl in range(2000 * ITERATIONS):
        sum_val = 0.0
        for base in range(0, LEN_1D, 4):
            partial = 0.0
            partial = partial + a[base + 0]
            partial = partial + a[base + 1]
            partial = partial + a[base + 2]
            partial = partial + a[base + 3]
            sum_val = sum_val + partial
        b[0] = sum_val

