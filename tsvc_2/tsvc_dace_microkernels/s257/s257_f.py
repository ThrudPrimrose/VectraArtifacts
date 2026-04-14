import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s257_f(
    a: dace.float32[LEN_2D],
    aa: dace.float32[LEN_2D, LEN_2D],
    bb: dace.float32[LEN_2D, LEN_2D],
):
    outer = 10 * (ITERATIONS // LEN_2D)
    for nl in range(outer):
        for i in range(8, LEN_2D):
            for j in range(LEN_2D):
                a[i] = aa[j, i] - a[i - 1]
                aa[j, i] = a[i] + bb[j, i]

