import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s3113_d(a: dace.float64[LEN_1D], b: dace.float64[2]):
    maxv = dace.float64(0)
    for nl in range(ITERATIONS * 4):
        maxv = abs(a[0])
        for i in range(LEN_1D):
            av = abs(a[i])
            if av > maxv:
                maxv = av
    b[0] = maxv

