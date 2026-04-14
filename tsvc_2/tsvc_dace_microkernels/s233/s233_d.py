import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s233_d(
    aa: dace.float64[LEN_2D, LEN_2D],
    bb: dace.float64[LEN_2D, LEN_2D],
    cc: dace.float64[LEN_2D, LEN_2D],
):
    for nl in range(100 * (ITERATIONS // LEN_2D)):
        for i in range(8, LEN_2D):
            for j in range(8, LEN_2D):
                aa[j, i] = aa[j - 1, i] + cc[j, i]
            for j in range(8, LEN_2D):
                bb[j, i] = bb[j, i - 1] + cc[j, i]

