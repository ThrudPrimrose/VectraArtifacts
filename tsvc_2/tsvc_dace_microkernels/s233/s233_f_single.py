import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")

@dace.program
def s233_f_single(
    aa: dace.float32[LEN_2D, LEN_2D],
    bb: dace.float32[LEN_2D, LEN_2D],
    cc: dace.float32[LEN_2D, LEN_2D],
):
    for i in range(8, LEN_2D):
        for j in range(8, LEN_2D):
            aa[j, i] = aa[j - 1, i] + cc[j, i]
        for j in range(8, LEN_2D):
            bb[j, i] = bb[j, i - 1] + cc[j, i]

