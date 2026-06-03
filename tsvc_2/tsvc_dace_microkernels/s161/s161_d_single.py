import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def s161_d_single(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    # ``c[i + 1]`` write: loop to ``LEN_1D - 1`` so the store stays in
    # bounds (upstream TSVC s161 loops ``i < LEN_1D - 1``; the original
    # port mis-transcribed this as ``range(LEN_1D)``, writing ``c[LEN_1D]``).
    for i in range(LEN_1D - 1):
        if b[i] < 0.0:
            c[i + 1] = a[i] + d[i] * d[i]
        else:
            a[i] = c[i] + d[i] * e[i]

