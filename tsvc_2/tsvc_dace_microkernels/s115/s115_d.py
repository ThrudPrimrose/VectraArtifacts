import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s115_d(a: dace.float64[LEN_2D], aa: dace.float64[LEN_2D, LEN_2D]):
    for nl in range(1000 * (ITERATIONS // LEN_2D)):
        for j in range(LEN_2D):
            for i in range(j + 1, LEN_2D):
                a[i] = a[i] - aa[j, i] * a[j]

