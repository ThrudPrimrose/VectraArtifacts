import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")
VLEN = 8

@dace.program
def s114_d_single(aa: dace.float64[LEN_2D, LEN_2D], bb: dace.float64[LEN_2D, LEN_2D]):
    for i in range(LEN_2D // VLEN):
        for j in range(i * VLEN):
            aa[i, j] = aa[j, i] + bb[i, j]

