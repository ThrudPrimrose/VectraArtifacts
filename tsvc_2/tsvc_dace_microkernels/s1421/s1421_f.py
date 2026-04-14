import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s1421_f(b: dace.float32[LEN_1D], a: dace.float32[LEN_1D]):
    half = LEN_1D // 2
    for nl in range(8 * ITERATIONS):
        for i in range(half):
            b[i] = b[half + i] + a[i]

