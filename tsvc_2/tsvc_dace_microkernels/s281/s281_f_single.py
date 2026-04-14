import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s281_f_single(
    a: dace.float32[LEN_1D], b: dace.float32[LEN_1D], c: dace.float32[LEN_1D]
):
    for i in range(LEN_1D):
        x = a[LEN_1D - i - 1] + b[i] * c[i]
        a[i] = x - 1.0
        b[i] = x

