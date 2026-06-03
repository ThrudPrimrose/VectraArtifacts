import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def ext_strided_store_2_d(src: dace.float64[LEN_1D], dst: dace.float64[2 * LEN_1D], scale: dace.float64):
    """``dst[i * 2] = src[i] * scale`` -- constant-stride sibling."""
    for i, in dace.map[0:LEN_1D:1]:
        dst[i * 2] = src[i] * scale

