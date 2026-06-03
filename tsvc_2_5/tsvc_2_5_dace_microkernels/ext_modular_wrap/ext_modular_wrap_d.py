import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
K = dace.symbol("K")

@dace.program
def ext_modular_wrap_d(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    """``a[(i + K) % LEN_1D] = b[i]`` -- modulo wraparound write. The
    write index is data-dependent through ``K``; the canonicalize
    pipeline's ``peel_limit`` knob unlocks parallelization by peeling
    the boundary iteration."""
    for i in range(LEN_1D):
        a[(i + K) % LEN_1D] = b[i]

