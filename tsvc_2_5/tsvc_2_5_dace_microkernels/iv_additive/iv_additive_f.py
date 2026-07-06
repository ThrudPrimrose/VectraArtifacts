import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def iv_additive_f(out: dace.float32[1]):
    """Additive induction variable: ``s = 0; for i in range(LEN_1D): s += 1.5``.
    Closed form ``s = 1.5 * LEN_1D``. The trip count is the symbol
    ``LEN_1D``; there is no per-element data, so the loop is a pure
    recurrence the substitution eliminates."""
    s = 0.0
    for i in range(LEN_1D):
        s = s + 1.5
    out[0] = s

