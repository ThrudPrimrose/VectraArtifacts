import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
SSYM = dace.symbol("SSYM")

@dace.program
def ext_strided_store_ssym_d(src: dace.float64[LEN_1D], dst: dace.float64[SSYM * LEN_1D], scale: dace.float64):
    """``dst[i * SSYM] = src[i] * scale``. The scatter is potentially
    non-permutation (depends on ``SSYM``); a safe lift requires a
    runtime guard ensuring distinct write indices."""
    for i, in dace.map[0:LEN_1D:1]:
        dst[i * SSYM] = src[i] * scale

