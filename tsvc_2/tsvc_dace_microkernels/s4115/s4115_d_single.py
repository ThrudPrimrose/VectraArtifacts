import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s4115_d_single(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    ip: dace.int32[LEN_1D],
    sum_out: dace.float64[1],
):
    sum_val = 0.0
    sum_val = 0.0
    for i in range(LEN_1D):
        sum_val = sum_val + a[i] * b[ip[i]]
    sum_out[0] = sum_val

