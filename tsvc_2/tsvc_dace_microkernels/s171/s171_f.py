import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s171_f(a: dace.float32[LEN_1D], b: dace.float32[LEN_1D], inc: dace.int64):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            a[i * inc] = a[i * inc] + b[i]

