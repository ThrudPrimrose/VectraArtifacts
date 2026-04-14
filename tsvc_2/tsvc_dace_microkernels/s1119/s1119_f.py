import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s1119_f(aa: dace.float32[LEN_2D, LEN_2D], bb: dace.float32[LEN_2D, LEN_2D]):
    for nl in range(200 * (ITERATIONS // LEN_2D)):
        for i in range(1, LEN_2D):
            for j in range(LEN_2D):
                aa[i, j] = aa[i - 1, j] + bb[i, j]

