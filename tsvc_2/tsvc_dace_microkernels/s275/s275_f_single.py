import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")

@dace.program
def s275_f_single(
    aa: dace.float32[LEN_2D, LEN_2D],
    bb: dace.float32[LEN_2D, LEN_2D],
    cc: dace.float32[LEN_2D, LEN_2D],
):
    for i in range(LEN_2D):
        if aa[0, i] > 0.0:
            for j in range(1, LEN_2D):
                aa[j, i] = aa[j - 1, i] + bb[j, i] * cc[j, i]

