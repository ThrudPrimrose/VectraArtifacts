import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s317_f(q: dace.float32[LEN_1D]):
    for nl in range(5 * ITERATIONS):
        q[0] = 1.0
        for i in range(LEN_1D // 2):
            q[0] = q[0] * 0.99

