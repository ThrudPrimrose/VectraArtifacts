import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s322_d_single(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], c: dace.float64[LEN_1D]
):
    for i in range(2, LEN_1D):
        a[i] = a[i] + a[i - 1] * b[i] + a[i - 2] * c[i]

