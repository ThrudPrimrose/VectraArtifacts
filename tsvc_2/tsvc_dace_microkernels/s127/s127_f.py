import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s127_f(
    a: dace.float32[LEN_1D],
    b: dace.float32[LEN_1D],
    c: dace.float32[LEN_1D],
    d: dace.float32[LEN_1D],
    e: dace.float32[LEN_1D],
):
    for nl in range(2 * ITERATIONS):
        for i in dace.map[0 : LEN_1D // 2]:
            a[2 * i] = b[i] + c[i] * d[i]
            a[2 * i + 1] = b[i] + d[i] * e[i]

