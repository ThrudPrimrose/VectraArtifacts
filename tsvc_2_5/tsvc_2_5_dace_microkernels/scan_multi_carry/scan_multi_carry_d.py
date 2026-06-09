import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def scan_multi_carry_d(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], x: dace.float64[LEN_1D],
                     y: dace.float64[LEN_1D]):
    """Two distinct unit-stride recurrences in one loop body: an additive
    scan on ``a`` and a multiplicative scan on ``b``. ``LoopToScan`` must
    emit two Scan libnodes with different operators (Add and Mul) from the
    same loop. Caller initializes ``a[0]`` and ``b[0]``."""
    for i in range(1, LEN_1D):
        a[i] = a[i - 1] + x[i]
        b[i] = b[i - 1] * y[i]

