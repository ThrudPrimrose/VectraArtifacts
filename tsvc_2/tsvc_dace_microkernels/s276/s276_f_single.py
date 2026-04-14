import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s276_f_single(
    a: dace.float32[LEN_1D],
    b: dace.float32[LEN_1D],
    c: dace.float32[LEN_1D],
    d: dace.float32[LEN_1D],
):
    mid = LEN_1D // 2
    for i in range(LEN_1D):
        if i + 1 < mid:
            a[i] = a[i] + b[i] * c[i]
        else:
            a[i] = a[i] + b[i] * d[i]

