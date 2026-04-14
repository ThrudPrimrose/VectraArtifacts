import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s174_f_single(a: dace.float32[LEN_1D], b: dace.float32[LEN_1D], M: dace.int64):
    for i in range(M):
        a[i + M] = a[i] + b[i]

