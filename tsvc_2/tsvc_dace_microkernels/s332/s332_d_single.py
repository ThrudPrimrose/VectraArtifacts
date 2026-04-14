import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s332_d_single(a: dace.float64[LEN_1D], result: dace.float64[1], threshold: dace.int64):
    index = -2
    value = -1.0
    for i in range(LEN_1D):
        if a[i] > threshold:
            index = i
            value = a[i]
            break
    result[0] = value + float(index)

