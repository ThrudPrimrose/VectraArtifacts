import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")

@dace.program
def s1115_f_single(
    aa: dace.float32[LEN_2D, LEN_2D],
    bb: dace.float32[LEN_2D, LEN_2D],
    cc: dace.float32[LEN_2D, LEN_2D],
):
    for i in range(LEN_2D):
        for j in range(LEN_2D):
            aa[i, j] = aa[i, j] * cc[j, i] + bb[i, j]

