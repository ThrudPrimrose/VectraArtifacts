import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
LEN_2D = dace.symbol("LEN_2D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s4116_f(
    a: dace.float32[LEN_1D],
    aa: dace.float32[LEN_2D, LEN_2D],
    ip: dace.int32[LEN_2D],
    j: dace.int32,
    inc: dace.int32,
    sum_out: dace.float32[1],
):
    sum_val = 0.0
    for nl in range(100 * ITERATIONS):
        sum_val = 0.0
        for i in range(LEN_2D - 1):
            off = inc + i
            sum_val = sum_val + a[off] * aa[j - 1, ip[i]]
    sum_out[0] = sum_val

