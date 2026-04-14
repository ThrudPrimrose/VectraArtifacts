import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s352_f(a: dace.float32[LEN_1D], b: dace.float32[LEN_1D], c: dace.float32[2]):
    dot = 0.0
    for nl in range(8 * ITERATIONS):
        dot = 0.0
        for i in range(0, LEN_1D, 4):
            dot = dot + (
                a[i] * b[i]
                + a[i + 1] * b[i + 1]
                + a[i + 2] * b[i + 2]
                + a[i + 3] * b[i + 3]
                + a[i + 4] * b[i + 4]
            )
    c[0] = dot

