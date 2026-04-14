import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_2D = dace.symbol("LEN_2D")

@dace.program
def vbor_d_single(
    a: dace.float64[LEN_2D],
    b: dace.float64[LEN_2D],
    c: dace.float64[LEN_2D],
    d: dace.float64[LEN_2D],
    e: dace.float64[LEN_2D],
    x: dace.float64[LEN_2D],
):
    for i in range(LEN_2D):
        a1 = a[i]
        b1 = b[i]
        c1 = c[i]
        d1 = d[i]
        e1 = e[i]
        f1 = a[i]
        a1 = (
            a1 * b1 * c1
            + a1 * b1 * d1
            + a1 * b1 * e1
            + a1 * b1 * f1
            + a1 * c1 * d1
            + a1 * c1 * e1
            + a1 * c1 * f1
            + a1 * d1 * e1
            + a1 * d1 * f1
            + a1 * e1 * f1
        )
        b1 = (
            b1 * c1 * d1
            + b1 * c1 * e1
            + b1 * c1 * f1
            + b1 * d1 * e1
            + b1 * d1 * f1
            + b1 * e1 * f1
        )
        c1 = c1 * d1 * e1 + c1 * d1 * f1 + c1 * e1 * f1
        d1 = d1 * e1 * f1
        x[i] = a1 * b1 * c1 * d1

