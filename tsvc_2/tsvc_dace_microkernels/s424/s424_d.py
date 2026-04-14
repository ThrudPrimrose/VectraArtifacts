import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
ITERATIONS = dace.symbol("ITERATIONS")

@dace.program
def s424_d(
    a: dace.float64[LEN_1D], xx: dace.float64[LEN_1D], flat: dace.float64[LEN_1D]
):
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D - 1):
            xx[i + 1] = flat[i] + a[i]

