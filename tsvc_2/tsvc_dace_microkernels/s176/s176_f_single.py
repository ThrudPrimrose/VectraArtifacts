import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s176_f_single(
    a: dace.float32[LEN_1D], b: dace.float32[LEN_1D], c: dace.float32[LEN_1D]
):
    m = LEN_1D // 2
    for j in range(LEN_1D // 2):
        for i in range(m):
            a[i] = a[i] + b[i + m - j - 1] * c[j]

