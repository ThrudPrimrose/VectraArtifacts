import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def ext_peel_multi_back_f(a: dace.float32[LEN_1D], b: dace.float32[LEN_1D]):
    """Two tail iterations write conflicting elements; peeling them off
    leaves a disjoint-write remainder that maps cleanly. Anchors the
    ``peel_limit >= 2`` requirement."""
    for i in range(LEN_1D):
        a[i] = b[i] * 2.0
        if i == LEN_1D - 1:
            a[LEN_1D - 2] = a[LEN_1D - 2] + 1.0
        elif i == LEN_1D - 2:
            a[LEN_1D - 3] = a[LEN_1D - 3] + 1.0

