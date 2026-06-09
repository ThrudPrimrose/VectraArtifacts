import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def scan_conditional_f(out: dace.float32[LEN_1D], delta: dace.float32[LEN_1D], mask: dace.int64[LEN_1D]):
    """Masked prefix scan: the running sum advances only where ``mask[i]``
    is set, otherwise it holds. ``LoopToScan`` must descend into the
    ConditionalBlock and treat the false branch as the additive identity.
    Caller seeds ``out[0]``."""
    for i in range(1, LEN_1D):
        if mask[i] > 0:
            out[i] = out[i - 1] + delta[i]
        else:
            out[i] = out[i - 1]

