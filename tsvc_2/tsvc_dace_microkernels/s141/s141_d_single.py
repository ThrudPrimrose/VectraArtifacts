import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")

@dace.program
def s141_d_single(
    bb: dace.float64[LEN_2D, LEN_2D], flat_2d_array: dace.float64[LEN_2D * LEN_2D]
):
    for i in range(LEN_2D):
        k = (i + 1) * i // 2 + i
        for j in range(i, LEN_2D):
            flat_2d_array[k] = flat_2d_array[k] + bb[j, i]
            k = k + j + 1

