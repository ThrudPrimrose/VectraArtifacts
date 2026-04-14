import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s424_f_single(
    a: dace.float32[LEN_1D], xx: dace.float32[LEN_1D], flat: dace.float32[LEN_1D]
):
    for i in range(LEN_1D - 1):
        xx[i + 1] = flat[i] + a[i]

