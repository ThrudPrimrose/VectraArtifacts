import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s4113_d_single(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    ip: dace.int32[LEN_1D],
):
    for i in range(LEN_1D):
        a[ip[i]] = b[ip[i]] + c[i]

