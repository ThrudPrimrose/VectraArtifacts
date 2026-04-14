import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s175_f_single(a: dace.float32[LEN_1D], b: dace.float32[LEN_1D], inc: dace.int64):
    for i in range(0, LEN_1D - inc, inc):
        a[i] = a[i + inc] + b[i]

