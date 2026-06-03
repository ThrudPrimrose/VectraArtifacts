import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def ext_scatter_store_d(src: dace.float64[LEN_1D], idx: dace.int64[LEN_1D], dst: dace.float64[LEN_1D],
                      scale: dace.float64):
    """``dst[idx[i]] = src[i] * scale``. Safe parallelization requires
    proving that ``idx`` is a permutation -- the ScatterToGuardedMaps
    pass emits a sort+duplicate-count check that lets the lift fire
    only when the runtime indices are distinct."""
    for i, in dace.map[0:LEN_1D:1]:
        dst[idx[i]] = src[i] * scale

