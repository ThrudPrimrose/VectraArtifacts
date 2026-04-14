import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s491_f(
    a: dace.float32[LEN_1D],
    b: dace.float32[LEN_1D],
    c: dace.float32[LEN_1D],
    d: dace.float32[LEN_1D],
    ip: dace.int32[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            a[ip[i]] = b[i] + c[i] * d[i]

