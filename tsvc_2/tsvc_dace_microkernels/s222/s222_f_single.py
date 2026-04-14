import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s222_f_single(
    a: dace.float32[LEN_1D],
    b: dace.float32[LEN_1D],
    c: dace.float32[LEN_1D],
    e: dace.float32[LEN_1D],
):
    for i in range(1, LEN_1D):
        a[i] = a[i] + b[i] * c[i]
        e[i] = e[i - 1] * e[i - 1]
        a[i] = a[i] - b[i] * c[i]

