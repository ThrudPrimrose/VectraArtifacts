import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def ext_strided_load_2_d(src: dace.float64[2 * LEN_1D], dst: dace.float64[LEN_1D], scale: dace.float64):
    """``dst[i] = src[i * 2] * scale`` -- the constant-stride sibling
    of ``ext_strided_load_ssym``. Most compilers vectorize this via
    ``vpcompressd``-style gathers."""
    for i, in dace.map[0:LEN_1D:1]:
        dst[i] = src[i * 2] * scale

