import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s471_f_single(
    x: dace.float32[LEN_1D],
    b: dace.float32[LEN_1D],
    c: dace.float32[LEN_1D],
    d: dace.float32[LEN_1D],
    e: dace.float32[LEN_1D],
):
    for i in range(LEN_1D):
        x[i] = b[i] + d[i] * d[i]
        b[i] = c[i] + d[i] * e[i]

