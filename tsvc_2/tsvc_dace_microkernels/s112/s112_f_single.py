import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s112_f_single(a: dace.float32[LEN_1D], b: dace.float32[LEN_1D]):
    for i in range(LEN_1D - 2, -1, -1):
        a[i + 1] = a[i] + b[i]

