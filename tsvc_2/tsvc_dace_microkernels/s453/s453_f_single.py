import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s453_f_single(a: dace.float32[LEN_1D], b: dace.float32[LEN_1D]):
    s = 0.0
    for i in range(LEN_1D):
        s = s + 2.0
        a[i] = s * b[i]

