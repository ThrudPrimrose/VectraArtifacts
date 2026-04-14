import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s311_f_single(a: dace.float32[LEN_1D], sum_out: dace.float32[LEN_1D]):
    sum_out[0] = 0.0
    for i in range(LEN_1D):
        sum_out[0] = sum_out[0] + a[i]

