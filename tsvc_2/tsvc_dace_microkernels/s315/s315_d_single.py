import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s315_d_single(a: dace.float64[LEN_1D], result: dace.float64[1]):
    for i in range(LEN_1D):
        a[i] = float((i * 7) % LEN_1D)
    x = a[0]
    index = 0
    for i in range(LEN_1D):
        if a[i] > x:
            x = a[i]
            index = i
    a[0] = x + float(index)
    result[0] = a[0]

