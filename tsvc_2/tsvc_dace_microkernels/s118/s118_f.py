import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s118_f(a: dace.float32[LEN_2D], bb: dace.float32[LEN_2D, LEN_2D]):
    for nl in range(200 * (ITERATIONS // LEN_2D)):
        for i in range(1, LEN_2D):
            for j in range(0, i):
                a[i] = a[i] + bb[j, i] * a[i - j - 1]

