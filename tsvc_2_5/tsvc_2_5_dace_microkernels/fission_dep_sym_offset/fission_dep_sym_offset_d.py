import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
K = dace.symbol("K")

@dace.program
def fission_dep_sym_offset_d(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], x: dace.float64[LEN_1D],
                           y: dace.float64[LEN_1D], z: dace.float64[LEN_1D]):
    """Same shape as :func:`fission_dep_const_offset` but the offset is
    the runtime symbol ``K``. Caller initializes ``a[0..K-1]`` before
    invocation."""
    for i in range(K, LEN_1D):
        a[i] = a[i - K] + x[i]
        b[i] = y[i] * z[i]

