import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s2102_f(aa: dace.float32[LEN_2D, LEN_2D]):
    for nl in range(100 * (ITERATIONS // LEN_2D)):
        for i in range(LEN_2D):
            for j in range(LEN_2D):
                aa[j, i] = 0.0
            aa[i, i] = 1.0

