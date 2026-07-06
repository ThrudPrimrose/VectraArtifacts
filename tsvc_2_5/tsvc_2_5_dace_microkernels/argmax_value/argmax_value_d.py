import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def argmax_value_d(a: dace.float64[LEN_1D], out: dace.float64[1]):
    """TSVC ``s314``: running maximum carried in a scalar.
    ``x = a[0]; for i in range(1, LEN_1D): if a[i] > x: x = a[i]``.
    ``ArgMaxLift`` rewrites this to ``Reduce(Max, a)``."""
    x = a[0]
    for i in range(1, LEN_1D):
        if a[i] > x:
            x = a[i]
    out[0] = x

