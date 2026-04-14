import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s316_d_single(a: dace.float64[LEN_1D], result: dace.float64[1]):
    x = a[0]
    for i in range(1, LEN_1D):
        if a[i] < x:
            x = a[i]
    result[0] = x

