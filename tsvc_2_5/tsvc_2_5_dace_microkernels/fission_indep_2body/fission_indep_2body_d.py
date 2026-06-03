import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def fission_indep_2body_d(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], x: dace.float64[LEN_1D],
                        y: dace.float64[LEN_1D], z: dace.float64[LEN_1D]):
    """Two independent writes sharing three reads. Either fused or
    fissioned bodies are correct; fission gives both bodies independent
    vector loops if register / reuse pressure forces the split."""
    for i in range(LEN_1D):
        a[i] = x[i] * y[i] + z[i]
        b[i] = x[i] - y[i] * z[i]

