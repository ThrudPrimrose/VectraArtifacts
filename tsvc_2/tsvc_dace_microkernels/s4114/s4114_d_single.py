import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s4114_d_single(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d_: dace.float64[LEN_1D],
    ip: dace.int32[LEN_1D],
    n1: dace.int32,
):
    for i in range(n1 - 1, LEN_1D):
        k = ip[i]
        a[i] = b[i] + c[LEN_1D - k - 1] * d_[i]

