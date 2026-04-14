import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s162_f_single(
    a: dace.float32[LEN_1D],
    b: dace.float32[LEN_1D],
    c: dace.float32[LEN_1D],
    k: dace.int64,
):
    if k > 0:
        for i in range(0, LEN_1D - k):
            a[i] = a[i + k] + b[i] * c[i]

