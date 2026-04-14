import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s3111_d(a: dace.float64[LEN_1D], b: dace.float64[2]):
    for nl in range(ITERATIONS // 2):
        sum_val = 0.0
        for i in range(LEN_1D):
            if a[i] > 0.0:
                sum_val = sum_val + a[i]
        b[0] = sum_val

