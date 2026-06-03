import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def masked_store_const_d(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], mask: dace.int64[LEN_1D]):
    """Predicated store with an integer mask: ``if mask[i] > 0: a[i] = b[i]``.
    Requires masked-store / blend-store vector intrinsics."""
    for i in dace.map[0:LEN_1D]:
        if mask[i] > 0:
            a[i] = b[i]

