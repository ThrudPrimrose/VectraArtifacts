from math import sqrt, exp

import dace
import numpy as np

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def ecrad_clamped_reduction_d(x: dace.float64[LEN_1D], y: dace.float64[LEN_1D], d: dace.float64[LEN_1D],
                            out: dace.float64[LEN_1D]):
    """ECRAD-shaped per-element clamped transmittance:
    ``out[i] = clamp(exp(-sqrt(max(x*x + y*y, 1e-12)) * d), 0, 1)``.

    Two ``max``/``min`` clamps + an ``exp`` + a ``sqrt`` in the body
    stress the transcendental-clamp recognizer and the SLEEF / libmvec
    intrinsic lowerings.
    """
    for i in dace.map[0:LEN_1D]:
        k = sqrt(max(x[i] * x[i] + y[i] * y[i], 1e-12))
        e = exp(-k * d[i])
        out[i] = max(0.0, min(e, 1.0))

