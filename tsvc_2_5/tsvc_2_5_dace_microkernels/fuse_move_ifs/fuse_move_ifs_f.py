import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")
K = dace.symbol("K")

@dace.program
def fuse_move_ifs_f(a: dace.float32[LEN_2D, LEN_2D], b: dace.float32[LEN_2D, LEN_2D], src: dace.float32[LEN_2D, LEN_2D],
                  cond: dace.float32[LEN_2D]):
    """Follow-up to :func:`move_if_data_dep_nest`: two loop nests whose
    guards block fusion. The first nest has a data-dependent guard
    ``cond[i]`` in the middle (``for i: if cond[i] > 0: for j: ...``); the
    second has a loop-invariant guard ``K`` wrapping the whole nest
    (``if K > 0: for i: for j: ...``). Moving BOTH guards to the innermost
    position rewrites each to the same ``for i: for j: if ...:`` shape,
    after which the two nests -- now sharing one iteration space -- fuse
    into a single ``for i: for j:`` carrying both predicated bodies: one
    parallel Map / GPU grid instead of two. ``K`` is bound at call time;
    rows/cells whose guard is false leave their output untouched (caller
    pre-fills ``a`` and ``b``)."""
    for i in range(LEN_2D):
        if cond[i] > 0.0:
            for j in range(LEN_2D):
                a[i, j] = src[i, j] * 2.0
    if K > 0:
        for i in range(LEN_2D):
            for j in range(LEN_2D):
                b[i, j] = src[i, j] + 1.0

