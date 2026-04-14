import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s421_f_single(a: dace.float32[LEN_1D], flat_2d_array: dace.float32[LEN_1D]):
    for i in range(LEN_1D - 1):
        flat_2d_array[i] = flat_2d_array[i + 1] + a[i]

