import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s232_d(aa: dace.float64[LEN_2D, LEN_2D], bb: dace.float64[LEN_2D, LEN_2D]):
    for nl in range(100 * (ITERATIONS // LEN_2D)):
        for j in range(1, LEN_2D):
            for i in range(1, j + 1):
                aa[j, i] = aa[j, i - 1] * aa[j, i - 1] + bb[j, i]

