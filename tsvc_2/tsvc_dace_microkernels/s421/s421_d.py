import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s421_d(a: dace.float64[LEN_1D], flat_2d_array: dace.float64[LEN_1D]):
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D - 1):
            flat_2d_array[i] = flat_2d_array[i + 1] + a[i]

