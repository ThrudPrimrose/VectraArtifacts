import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s126_d(
    bb: dace.float64[LEN_2D, LEN_2D],
    flat_2d_array: dace.float64[LEN_2D * LEN_2D],
    cc: dace.float64[LEN_2D, LEN_2D],
):
    for nl in range(10 * (ITERATIONS // LEN_2D)):
        k = 1
        for i in range(LEN_2D):
            for j in range(1, LEN_2D):
                bb[j, i] = bb[j - 1, i] + flat_2d_array[k - 1] * cc[j, i]
                k = k + 1
            k = k + 1

