import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s2711_f_single(
    a: dace.float32[LEN_1D], b: dace.float32[LEN_1D], c: dace.float32[LEN_1D]
):
    for i in range(LEN_1D):
        if b[i] != 0.0:
            a[i] = a[i] + b[i] * c[i]

