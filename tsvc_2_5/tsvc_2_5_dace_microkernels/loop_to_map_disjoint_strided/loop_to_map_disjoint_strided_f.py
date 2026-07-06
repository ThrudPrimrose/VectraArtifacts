import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def loop_to_map_disjoint_strided_f(a: dace.float32[2 * LEN_1D], b: dace.float32[LEN_1D]):
    """Two strided writes per iteration to disjoint slots ``a[2*i]`` and
    ``a[2*i+1]``. A gcd-based disjointness proof (the two write index sets
    never collide) lets ``LoopToMap`` parallelize despite the
    two-writes-per-iteration shape."""
    for i in range(LEN_1D):
        a[2 * i] = b[i] + 1.0
        a[2 * i + 1] = b[i] * 2.0

