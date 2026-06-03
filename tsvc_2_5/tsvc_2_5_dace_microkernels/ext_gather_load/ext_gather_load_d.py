import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def ext_gather_load_d(src: dace.float64[LEN_1D], idx: dace.int64[LEN_1D], dst: dace.float64[LEN_1D], scale: dace.float64):
    """``dst[i] = src[idx[i]] * scale``. The read pattern is fully
    data-dependent; vectorization requires a gather intrinsic."""
    for i, in dace.map[0:LEN_1D:1]:
        dst[i] = src[idx[i]] * scale

