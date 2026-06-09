import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")

@dace.program
def reroll_saxpy4_d(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    """TSVC ``s351``: a saxpy hand-unrolled 4x. Four structurally-identical
    lanes at offsets ``{0, 1, 2, 3}`` over a step-4 loop look like one
    strided ``4*i + k`` access that blocks ``LoopToMap``;
    ``RerollUnrolledLoops`` re-rolls to a unit-step loop first. Requires
    ``LEN_1D`` divisible by 4."""
    for i in range(0, LEN_1D, 4):
        a[i] = a[i] + b[i] * 2.0
        a[i + 1] = a[i + 1] + b[i + 1] * 2.0
        a[i + 2] = a[i + 2] + b[i + 2] * 2.0
        a[i + 3] = a[i + 3] + b[i + 3] * 2.0

