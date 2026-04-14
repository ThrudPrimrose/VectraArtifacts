import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s231_f(aa: dace.float32[LEN_2D, LEN_2D], bb: dace.float32[LEN_2D, LEN_2D]):
    for nl in range(100 * (ITERATIONS // LEN_2D)):
        for i in range(LEN_2D):
            for j in range(1, LEN_2D):
                aa[j, i] = aa[j - 1, i] + bb[j, i]

