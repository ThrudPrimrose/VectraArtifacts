import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
K = dace.symbol("K")

@dace.program
def masked_store_sym_d(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], threshold_data: dace.float64[LEN_1D]):
    """Predicated store keyed on a comparison against the symbolic
    threshold ``K`` (treated as a double scalar): ``if threshold_data[i]
    > K: a[i] = b[i]``."""
    for i in dace.map[0:LEN_1D]:
        if threshold_data[i] > K:
            a[i] = b[i]

