import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s132_d(
    aa: dace.float64[LEN_2D, LEN_2D], b: dace.float64[LEN_2D], c: dace.float64[LEN_2D]
):
    for nl in range(400 * ITERATIONS):
        for i in range(1, LEN_2D):
            aa[0, i] = aa[1, i - 1] + b[i] * c[1]

