import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")

@dace.program
def s115_f_single(a: dace.float32[LEN_2D], aa: dace.float32[LEN_2D, LEN_2D]):
    for j in range(LEN_2D):
        for i in range(j + 1, LEN_2D):
            a[i] = a[i] - aa[j, i] * a[j]

