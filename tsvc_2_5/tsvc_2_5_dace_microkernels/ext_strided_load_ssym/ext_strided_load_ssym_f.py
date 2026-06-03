import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
SSYM = dace.symbol("SSYM")

@dace.program
def ext_strided_load_ssym_f(src: dace.float32[SSYM * LEN_1D], dst: dace.float32[LEN_1D], scale: dace.float32):
    """``dst[i] = src[i * SSYM] * scale`` with ``SSYM`` a runtime symbol.

    The compiler cannot prove the access pattern is contiguous because
    ``SSYM`` is unknown; native auto-vectorizers fall back to scalar
    code unless they emit a runtime stride check + gather intrinsic.
    """
    for i, in dace.map[0:LEN_1D:1]:
        dst[i] = src[i * SSYM] * scale

