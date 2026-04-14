import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s423_f(a: dace.float32[LEN_1D], flat_2d_array: dace.float32[LEN_1D]):
    vl = 64
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D - 1):
            flat_2d_array[i + 1] = flat_2d_array[vl + i] + a[i]

