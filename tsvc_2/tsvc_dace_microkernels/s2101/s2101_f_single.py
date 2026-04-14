import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")

@dace.program
def s2101_f_single(
    aa: dace.float32[LEN_2D, LEN_2D],
    bb: dace.float32[LEN_2D, LEN_2D],
    cc: dace.float32[LEN_2D, LEN_2D],
):
    for i in range(LEN_2D):
        aa[i, i] = aa[i, i] + bb[i, i] * cc[i, i]

