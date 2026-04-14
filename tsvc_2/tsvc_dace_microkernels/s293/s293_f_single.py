import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s293_f_single(a: dace.float32[LEN_1D]):
    a0 = a[0]
    for i in range(LEN_1D):
        a[i] = a0

