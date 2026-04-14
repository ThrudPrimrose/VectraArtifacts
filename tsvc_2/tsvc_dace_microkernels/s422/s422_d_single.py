import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s422_d_single(a: dace.float64[LEN_1D], flat_2d_array: dace.float64[LEN_1D * LEN_1D]):
    for i in range(LEN_1D):
        flat_2d_array[4 + i] = flat_2d_array[8 + i] + a[i]

