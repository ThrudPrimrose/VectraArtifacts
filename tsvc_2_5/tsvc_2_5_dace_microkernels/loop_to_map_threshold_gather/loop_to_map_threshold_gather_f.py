import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")

@dace.program
def loop_to_map_threshold_gather_f(out: dace.float32[LEN_2D, LEN_2D], x: dace.float32[LEN_2D, LEN_2D],
                                 y: dace.float32[LEN_2D, LEN_2D], w: dace.float32[LEN_2D, LEN_2D],
                                 idx: dace.int64[LEN_2D]):
    """cloudsc-style column physics: for each ``(i, k)`` a threshold on
    GATHERED data ``w[idx[i], k]`` selects which elementwise update writes
    ``out[i, k]``. Every ``(i, k)`` owns a distinct output cell, so
    ``LoopToMap`` parallelizes the whole 2D nest even though the predicate
    reads through the indirection ``idx``."""
    for i in range(LEN_2D):
        for k in range(LEN_2D):
            if w[idx[i], k] > 0.5:
                out[i, k] = x[i, k] * 2.0
            else:
                out[i, k] = y[i, k] + 1.0

