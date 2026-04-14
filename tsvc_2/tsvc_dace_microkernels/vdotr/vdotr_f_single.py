import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def vdotr_f_single(
    a: dace.float32[LEN_1D], b: dace.float32[LEN_1D], dot_out: dace.float32[LEN_1D]
):
    dot_out[0] = 0.0
    dot_out[0] = 0.0
    for i in range(LEN_1D):
        dot_out[0] = dot_out[0] + a[i] * b[i]

