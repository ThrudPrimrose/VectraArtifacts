import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s1251_f_single(
    a: dace.float32[LEN_1D],
    b: dace.float32[LEN_1D],
    c: dace.float32[LEN_1D],
    d: dace.float32[LEN_1D],
    e: dace.float32[LEN_1D],
):
    for i in range(LEN_1D):
        s = b[i] + c[i]
        b[i] = a[i] + d[i]
        a[i] = s * e[i]

