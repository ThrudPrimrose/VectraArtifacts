import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
S = dace.symbol('S')

@dace.program
def vpvts_f_single(a: dace.float32[LEN_1D], b: dace.float32[LEN_1D]):
    for i in range(LEN_1D):
        a[i] = a[i] + b[i] * S

