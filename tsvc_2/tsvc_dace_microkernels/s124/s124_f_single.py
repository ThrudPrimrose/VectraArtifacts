import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s124_f_single(
    a: dace.float32[LEN_1D],
    b: dace.float32[LEN_1D],
    c: dace.float32[LEN_1D],
    d: dace.float32[LEN_1D],
    e: dace.float32[LEN_1D],
):
    j = -1
    for i in range(LEN_1D):
        if b[i] > 0.0:
            j = j + 1
            a[j] = b[i] + d[i] * e[i]
        else:
            j = j + 1
            a[j] = c[i] + d[i] * e[i]

