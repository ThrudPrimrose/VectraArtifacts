# Copyright 2019-2025 ETH Zurich and the DaCe authors. All rights reserved.
# All 151 TSVC @dace.program kernel definitions.
# No test functions, no compile infrastructure.

import dace
import numpy as np
from math import sin, cos, log, exp, pow

LEN_1D = dace.symbol("LEN_1D")
LEN_2D = dace.symbol("LEN_2D")
ITERATIONS = dace.symbol("ITERATIONS")
S = dace.symbol("S")
VLEN = 8


# ==========================================================================
#  %1.1  Linear dependence testing
# ==========================================================================


@dace.program
def dace_s000(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(2 * ITERATIONS):
        for i in range(LEN_1D):
            a[i] = b[i] + 1.0


@dace.program
def dace_s111(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(2 * ITERATIONS):
        for i in range(1, LEN_1D, 2):
            a[i] = a[i - 1] + b[i]


@dace.program
def dace_s1111(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
):
    for nl in range(2 * ITERATIONS):
        for i in dace.map[0 : LEN_1D // 2]:
            a[2 * i] = (
                c[i] * b[i] + d[i] * b[i] + c[i] * c[i] + d[i] * b[i] + d[i] * c[i]
            )


@dace.program
def dace_s112(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(3 * ITERATIONS):
        for i in range(LEN_1D - 2, -1, -1):
            a[i + 1] = a[i] + b[i]


@dace.program
def dace_s1112(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(ITERATIONS * 3):
        for i in range(LEN_1D - 1, -1, -1):
            a[i] = b[i] + 1.0


@dace.program
def dace_s113(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(4 * ITERATIONS):
        for i in range(1, LEN_1D):
            a[i] = a[0] + b[i]


@dace.program
def dace_s1113(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(2 * ITERATIONS):
        for i in range(LEN_1D):
            a[i] = a[LEN_1D // 2] + b[i]


@dace.program
def dace_s114(aa: dace.float64[LEN_2D, LEN_2D], bb: dace.float64[LEN_2D, LEN_2D]):
    for nl in range(200 * (ITERATIONS // LEN_2D)):
        for i in range(LEN_2D // VLEN):
            for j in range(i * VLEN):
                aa[i, j] = aa[j, i] + bb[i, j]


@dace.program
def dace_s115(a: dace.float64[LEN_2D], aa: dace.float64[LEN_2D, LEN_2D]):
    for nl in range(1000 * (ITERATIONS // LEN_2D)):
        for j in range(LEN_2D):
            for i in range(j + 1, LEN_2D):
                a[i] = a[i] - aa[j, i] * a[j]


@dace.program
def dace_s1115(
    aa: dace.float64[LEN_2D, LEN_2D],
    bb: dace.float64[LEN_2D, LEN_2D],
    cc: dace.float64[LEN_2D, LEN_2D],
):
    for nl in range(100 * (ITERATIONS // LEN_2D)):
        for i in range(LEN_2D):
            for j in range(LEN_2D):
                aa[i, j] = aa[i, j] * cc[j, i] + bb[i, j]


@dace.program
def dace_s116(a: dace.float64[LEN_1D]):
    for nl in range(ITERATIONS * 10):
        for i in range(0, LEN_1D - 4, 4):
            a[i] = a[i + 1] * a[i]
            a[i + 1] = a[i + 2] * a[i + 1]
            a[i + 2] = a[i + 3] * a[i + 2]
            a[i + 3] = a[i + 4] * a[i + 3]


@dace.program
def dace_s118(a: dace.float64[LEN_2D], bb: dace.float64[LEN_2D, LEN_2D]):
    for nl in range(200 * (ITERATIONS // LEN_2D)):
        for i in range(1, LEN_2D):
            for j in range(0, i):
                a[i] = a[i] + bb[j, i] * a[i - j - 1]


@dace.program
def dace_s119(aa: dace.float64[LEN_2D, LEN_2D], bb: dace.float64[LEN_2D, LEN_2D]):
    for nl in range(200 * (ITERATIONS // LEN_2D)):
        for i in range(1, LEN_2D):
            for j in range(1, LEN_2D):
                aa[i, j] = aa[i - 1, j - 1] + bb[i, j]


@dace.program
def dace_s1119(aa: dace.float64[LEN_2D, LEN_2D], bb: dace.float64[LEN_2D, LEN_2D]):
    for nl in range(200 * (ITERATIONS // LEN_2D)):
        for i in range(1, LEN_2D):
            for j in range(LEN_2D):
                aa[i, j] = aa[i - 1, j] + bb[i, j]


# ==========================================================================
#  %1.2  Induction variable recognition
# ==========================================================================


@dace.program
def dace_s121(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(3 * ITERATIONS):
        for i in range(LEN_1D - 1):
            j = i + 1
            a[i] = a[j] + b[i]


@dace.program
def dace_s122(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], n1: dace.int64, n3: dace.int64
):
    for nl in range(ITERATIONS):
        j = 1
        k = 0
        for i in range(n1 - 1, LEN_1D, n3):
            k = k + j
            a[i] = a[i] + b[LEN_1D - k]


@dace.program
def dace_s123(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        j = -1
        for i in range(LEN_1D // 2):
            j = j + 1
            a[j] = b[i] + d[i] * e[i]
            if c[i] > 0.0:
                j = j + 1
                a[j] = c[i] + d[i] * e[i]


@dace.program
def dace_s124(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        j = -1
        for i in range(LEN_1D):
            if b[i] > 0.0:
                j = j + 1
                a[j] = b[i] + d[i] * e[i]
            else:
                j = j + 1
                a[j] = c[i] + d[i] * e[i]


@dace.program
def dace_s125(
    flat_2d_array: dace.float64[LEN_2D * LEN_2D],
    aa: dace.float64[LEN_2D, LEN_2D],
    bb: dace.float64[LEN_2D, LEN_2D],
    cc: dace.float64[LEN_2D, LEN_2D],
):
    for nl in range(100 * (ITERATIONS // LEN_2D)):
        k = -1
        for i in range(LEN_2D):
            for j in range(LEN_2D):
                k = k + 1
                flat_2d_array[k] = aa[i, j] + bb[i, j] * cc[i, j]


@dace.program
def dace_s126(
    bb: dace.float64[LEN_2D, LEN_2D],
    flat_2d_array: dace.float64[LEN_2D * LEN_2D],
    cc: dace.float64[LEN_2D, LEN_2D],
):
    for nl in range(10 * (ITERATIONS // LEN_2D)):
        k = 1
        for i in range(LEN_2D):
            for j in range(1, LEN_2D):
                bb[j, i] = bb[j - 1, i] + flat_2d_array[k - 1] * cc[j, i]
                k = k + 1
            k = k + 1


@dace.program
def dace_s127(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(2 * ITERATIONS):
        for i in dace.map[0 : LEN_1D // 2]:
            a[2 * i] = b[i] + c[i] * d[i]
            a[2 * i + 1] = b[i] + d[i] * e[i]


@dace.program
def dace_s128(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
):
    for nl in range(2 * ITERATIONS):
        j = -1
        for i in range(LEN_1D // 2):
            k = j + 1
            a[i] = b[k] - d[i]
            j = k + 1
            b[k] = a[i] + c[k]


# ==========================================================================
#  %1.3  Global data flow analysis
# ==========================================================================


@dace.program
def dace_s131(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(5 * ITERATIONS):
        for i in range(LEN_1D - 1):
            a[i] = a[i + 1] + b[i]


@dace.program
def dace_s132(
    aa: dace.float64[LEN_2D, LEN_2D], b: dace.float64[LEN_2D], c: dace.float64[LEN_2D]
):
    for nl in range(400 * ITERATIONS):
        for i in range(1, LEN_2D):
            aa[0, i] = aa[1, i - 1] + b[i] * c[1]


# ==========================================================================
#  %1.4  Nonlinear dependence testing
# ==========================================================================


@dace.program
def dace_s141(
    bb: dace.float64[LEN_2D, LEN_2D], flat_2d_array: dace.float64[LEN_2D * LEN_2D]
):
    for nl in range(200 * (ITERATIONS // LEN_2D)):
        for i in range(LEN_2D):
            k = (i + 1) * i // 2 + i
            for j in range(i, LEN_2D):
                flat_2d_array[k] = flat_2d_array[k] + bb[j, i]
                k = k + j + 1


# ==========================================================================
#  %1.5  Loop splitting / distribution
# ==========================================================================


@dace.program
def dace_s151(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(5 * ITERATIONS):
        for i in range(LEN_1D - 1):
            a[i] = a[i + 1] + b[i]


@dace.program
def dace_s152(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            b[i] = d[i] * e[i]
        for i in range(LEN_1D):
            a[i] = a[i] + b[i] * c[i]


# ==========================================================================
#  %1.6  Control flow
# ==========================================================================


@dace.program
def dace_s161(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS // 2):
        for i in range(LEN_1D):
            if b[i] < 0.0:
                c[i + 1] = a[i] + d[i] * d[i]
            else:
                a[i] = c[i] + d[i] * e[i]


@dace.program
def dace_s1161(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            if c[i] < 0.0:
                b[i] = a[i] + d[i] * d[i]
            else:
                a[i] = c[i] + d[i] * e[i]


@dace.program
def dace_s162(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    k: dace.int64,
):
    for nl in range(ITERATIONS):
        if k > 0:
            for i in range(0, LEN_1D - k):
                a[i] = a[i + k] + b[i] * c[i]


# ==========================================================================
#  %1.7  Symbolic resolution / strided access
# ==========================================================================


@dace.program
def dace_s171(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], inc: dace.int64):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            a[i * inc] = a[i * inc] + b[i]


@dace.program
def dace_s172(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], n1: dace.int64, n3: dace.int64
):
    for nl in range(ITERATIONS):
        for i in range(n1 - 1, LEN_1D, n3):
            a[i] = a[i] + b[i]


@dace.program
def dace_s173(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(10 * ITERATIONS):
        for i in range(LEN_1D // 2):
            a[i + (LEN_1D // 2)] = a[i] + b[i]


@dace.program
def dace_s174(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], M: dace.int64):
    for nl in range(10 * ITERATIONS):
        for i in range(M):
            a[i + M] = a[i] + b[i]


@dace.program
def dace_s175(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], inc: dace.int64):
    for nl in range(ITERATIONS):
        for i in range(0, LEN_1D - inc, inc):
            a[i] = a[i + inc] + b[i]


@dace.program
def dace_s176(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], c: dace.float64[LEN_1D]
):
    m = LEN_1D // 2
    outer = 4 * (ITERATIONS // LEN_1D)
    for nl in range(outer):
        for j in range(LEN_1D // 2):
            for i in range(m):
                a[i] = a[i] + b[i + m - j - 1] * c[j]


# ==========================================================================
#  %2.1  Statement reordering
# ==========================================================================


@dace.program
def dace_s211(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(1, LEN_1D - 1):
            a[i] = b[i - 1] + c[i] * d[i]
            b[i] = b[i + 1] - e[i] * d[i]


@dace.program
def dace_s212(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D - 1):
            a[i] = a[i] * c[i]
            b[i] = b[i] + (a[i + 1] * d[i])


@dace.program
def dace_s1213(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(1, LEN_1D - 1):
            a[i] = b[i - 1] + c[i]
            b[i] = a[i + 1] * d[i]


# ==========================================================================
#  %2.2  Loop distribution / recurrences
# ==========================================================================


@dace.program
def dace_s221(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS // 2):
        for i in range(1, LEN_1D):
            a[i] = a[i] + c[i] * d[i]
            b[i] = b[i - 1] + a[i] + d[i]


@dace.program
def dace_s1221(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(ITERATIONS):
        for i in range(4, LEN_1D):
            b[i] = b[i - 4] + a[i]


@dace.program
def dace_s222(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS // 2):
        for i in range(1, LEN_1D):
            a[i] = a[i] + b[i] * c[i]
            e[i] = e[i - 1] * e[i - 1]
            a[i] = a[i] - b[i] * c[i]


# ==========================================================================
#  %2.3  Loop interchange
# ==========================================================================


@dace.program
def dace_s231(aa: dace.float64[LEN_2D, LEN_2D], bb: dace.float64[LEN_2D, LEN_2D]):
    for nl in range(100 * (ITERATIONS // LEN_2D)):
        for i in range(LEN_2D):
            for j in range(1, LEN_2D):
                aa[j, i] = aa[j - 1, i] + bb[j, i]


@dace.program
def dace_s232(aa: dace.float64[LEN_2D, LEN_2D], bb: dace.float64[LEN_2D, LEN_2D]):
    for nl in range(100 * (ITERATIONS // LEN_2D)):
        for j in range(1, LEN_2D):
            for i in range(1, j + 1):
                aa[j, i] = aa[j, i - 1] * aa[j, i - 1] + bb[j, i]


@dace.program
def dace_s1232(
    aa: dace.float64[LEN_2D, LEN_2D],
    bb: dace.float64[LEN_2D, LEN_2D],
    cc: dace.float64[LEN_2D, LEN_2D],
):
    for nl in range(100 * (ITERATIONS // LEN_2D)):
        for j in range(LEN_2D):
            for i in range(j * VLEN, LEN_2D):
                aa[i, j] = bb[i, j] + cc[i, j]


@dace.program
def dace_s233(
    aa: dace.float64[LEN_2D, LEN_2D],
    bb: dace.float64[LEN_2D, LEN_2D],
    cc: dace.float64[LEN_2D, LEN_2D],
):
    for nl in range(100 * (ITERATIONS // LEN_2D)):
        for i in range(8, LEN_2D):
            for j in range(8, LEN_2D):
                aa[j, i] = aa[j - 1, i] + cc[j, i]
            for j in range(8, LEN_2D):
                bb[j, i] = bb[j, i - 1] + cc[j, i]


@dace.program
def dace_s2233(
    aa: dace.float64[LEN_2D, LEN_2D],
    bb: dace.float64[LEN_2D, LEN_2D],
    cc: dace.float64[LEN_2D, LEN_2D],
):
    for nl in range(100 * (ITERATIONS // LEN_2D)):
        for i in range(8, LEN_2D):
            for j in range(8, LEN_2D):
                aa[j, i] = aa[j - 1, i] + cc[j, i]
            for j in range(8, LEN_2D):
                bb[i, j] = bb[i - 1, j] + cc[i, j]


@dace.program
def dace_s235(
    a: dace.float64[LEN_2D],
    b: dace.float64[LEN_2D],
    c: dace.float64[LEN_2D],
    aa: dace.float64[LEN_2D, LEN_2D],
    bb: dace.float64[LEN_2D, LEN_2D],
):
    outer = 200 * (ITERATIONS // LEN_2D)
    for nl in range(outer):
        for i in range(LEN_2D):
            a[i] = a[i] + b[i] * c[i]
            for j in range(1, LEN_2D):
                aa[j, i] = aa[j - 1, i] + bb[j, i] * a[i]


# ==========================================================================
#  %2.4  Statement reordering + dependences
# ==========================================================================


@dace.program
def dace_s241(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
):
    outer = 2 * ITERATIONS
    for nl in range(outer):
        for i in range(LEN_1D - 1):
            a[i] = b[i] * c[i] * d[i]
            b[i] = a[i] * a[i + 1] * d[i]


@dace.program
def dace_s242(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
):
    outer = ITERATIONS // 5
    for nl in range(outer):
        for i in range(1, LEN_1D):
            a[i] = a[i - 1] + 0.5 + 1.0 + b[i] + c[i] + d[i]


@dace.program
def dace_s243(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D - 1):
            a[i] = b[i] + c[i] * d[i]
            b[i] = a[i] + d[i] * e[i]
            a[i] = b[i] + a[i + 1] * d[i]


@dace.program
def dace_s244(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D - 1):
            a[i] = b[i] + c[i] * d[i]
            b[i] = c[i] + b[i]
            a[i + 1] = b[i] + a[i + 1] * d[i]


@dace.program
def dace_s1244(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D - 1):
            a[i] = b[i] + c[i] * c[i] + b[i] * b[i] + c[i]
            d[i] = a[i] + a[i + 1]


@dace.program
def dace_s2244(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        a[LEN_1D - 1] = b[LEN_1D - 2] + e[LEN_1D - 2]
        for i in range(LEN_1D - 1):
            a[i] = b[i] + c[i]


# ==========================================================================
#  %2.5  Scalar expansion / privatization
# ==========================================================================


@dace.program
def dace_s251(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
):
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D):
            s = b[i] + c[i] * d[i]
            a[i] = s * s


@dace.program
def dace_s1251(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D):
            s = b[i] + c[i]
            b[i] = a[i] + d[i]
            a[i] = s * e[i]


@dace.program
def dace_s2251(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        s = 0.0
        for i in range(LEN_1D):
            a[i] = s * e[i]
            s = b[i] + c[i]
            b[i] = a[i] + d[i]


@dace.program
def dace_s3251(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D - 1):
            a[i + 1] = b[i] + c[i]
            b[i] = c[i] * e[i]
            d[i] = a[i] * e[i]


@dace.program
def dace_s252(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], c: dace.float64[LEN_1D]
):
    for nl in range(ITERATIONS):
        t = 0.0
        for i in range(LEN_1D):
            s = b[i] * c[i]
            a[i] = s + t
            t = s


@dace.program
def dace_s253(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            if a[i] > b[i]:
                s = a[i] - b[i] * d[i]
                c[i] = c[i] + s
                a[i] = s


@dace.program
def dace_s254(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(4 * ITERATIONS):
        x = b[LEN_1D - 1]
        for i in range(LEN_1D):
            a[i] = (b[i] + x) * 0.5
            x = b[i]


@dace.program
def dace_s255(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(ITERATIONS):
        x = b[LEN_1D - 1]
        y = b[LEN_1D - 2]
        for i in range(LEN_1D):
            a[i] = (b[i] + x + y) * 0.333
            y = x
            x = b[i]


@dace.program
def dace_s256(
    a: dace.float64[LEN_2D],
    aa: dace.float64[LEN_2D, LEN_2D],
    bb: dace.float64[LEN_2D, LEN_2D],
    d: dace.float64[LEN_2D],
):
    outer = 10 * (ITERATIONS // LEN_2D)
    for nl in range(outer):
        for i in range(LEN_2D):
            for j in range(1, LEN_2D):
                a[j] = 1.0 - a[j - 1]
                aa[j, i] = a[j] + bb[j, i] * d[j]


@dace.program
def dace_s257(
    a: dace.float64[LEN_2D],
    aa: dace.float64[LEN_2D, LEN_2D],
    bb: dace.float64[LEN_2D, LEN_2D],
):
    outer = 10 * (ITERATIONS // LEN_2D)
    for nl in range(outer):
        for i in range(8, LEN_2D):
            for j in range(LEN_2D):
                a[i] = aa[j, i] - a[i - 1]
                aa[j, i] = a[i] + bb[j, i]


@dace.program
def dace_s258(
    a: dace.float64[LEN_2D],
    b: dace.float64[LEN_2D],
    c: dace.float64[LEN_2D],
    d: dace.float64[LEN_2D],
    e: dace.float64[LEN_2D],
    aa: dace.float64[1, LEN_2D],
):
    for nl in range(ITERATIONS):
        s = 0.0
        for i in range(LEN_2D):
            if a[i] > 0.0:
                s = d[i] * d[i]
            b[i] = s * c[i] + d[i]
            e[i] = (s + 1.0) * aa[0, i]


# ==========================================================================
#  %2.6  Coupled subscripts
# ==========================================================================


@dace.program
def dace_s261(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(1, LEN_1D):
            t = a[i] + b[i]
            a[i] = t + c[i - 1]
            c[i] = c[i] * d[i]


# ==========================================================================
#  %2.7  Control flow in vectorizable loops
# ==========================================================================


@dace.program
def dace_s271(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], c: dace.float64[LEN_1D]
):
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D):
            if b[i] > 0.0:
                a[i] = a[i] + b[i] * c[i]


@dace.program
def dace_s272(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
    threshold: dace.int64,
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            if e[i] >= threshold:
                a[i] = a[i] + c[i] * d[i]
                b[i] = b[i] + c[i] * c[i]


@dace.program
def dace_s273(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            a[i] = a[i] + d[i] * e[i]
            if a[i] < 0.0:
                b[i] = b[i] + d[i] * e[i]
            c[i] = c[i] + a[i] * d[i]


@dace.program
def dace_s274(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            a[i] = c[i] + e[i] * d[i]
            if a[i] > 0.0:
                b[i] = a[i] + b[i]
            else:
                a[i] = d[i] * e[i]


@dace.program
def dace_s275(
    aa: dace.float64[LEN_2D, LEN_2D],
    bb: dace.float64[LEN_2D, LEN_2D],
    cc: dace.float64[LEN_2D, LEN_2D],
):
    outer = 10 * (ITERATIONS // LEN_2D)
    for nl in range(outer):
        for i in range(LEN_2D):
            if aa[0, i] > 0.0:
                for j in range(1, LEN_2D):
                    aa[j, i] = aa[j - 1, i] + bb[j, i] * cc[j, i]


@dace.program
def dace_s2275(
    a: dace.float64[LEN_2D],
    b: dace.float64[LEN_2D],
    c: dace.float64[LEN_2D],
    d: dace.float64[LEN_2D],
    aa: dace.float64[LEN_2D, LEN_2D],
    bb: dace.float64[LEN_2D, LEN_2D],
    cc: dace.float64[LEN_2D, LEN_2D],
):
    for nl in range(100 * (ITERATIONS // LEN_2D)):
        for i in range(LEN_2D):
            for j in range(LEN_2D):
                aa[j, i] = aa[j, i] + bb[j, i] * cc[j, i]
            a[i] = b[i] + c[i] * d[i]


@dace.program
def dace_s276(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
):
    mid = LEN_1D // 2
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D):
            if i + 1 < mid:
                a[i] = a[i] + b[i] * c[i]
            else:
                a[i] = a[i] + b[i] * d[i]


@dace.program
def dace_s277(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D - 1):
            if a[i] < 0.0:
                if b[i] < 0.0:
                    a[i] = a[i] + c[i] * d[i]
                b[i + 1] = c[i] + d[i] * e[i]


@dace.program
def dace_s278(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            if a[i] > 0.0:
                c[i] = -c[i] + d[i] * e[i]
            else:
                b[i] = -b[i] + d[i] * e[i]
            a[i] = b[i] + c[i] * d[i]


@dace.program
def dace_s279(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS // 2):
        for i in range(LEN_1D):
            if a[i] > 0.0:
                c[i] = -c[i] + e[i] * e[i]
            else:
                b[i] = -b[i] + d[i] * d[i]
                if b[i] > a[i]:
                    c[i] = c[i] + d[i] * e[i]
            a[i] = b[i] + c[i] * d[i]


@dace.program
def dace_s1279(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            if a[i] < 0.0:
                if b[i] > a[i]:
                    c[i] = c[i] + d[i] * e[i]


@dace.program
def dace_s2710(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
    x: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS // 2):
        for i in range(LEN_1D):
            if a[i] > b[i]:
                a[i] = a[i] + b[i] * d[i]
                if LEN_1D > 10:
                    c[i] = c[i] + d[i] * d[i]
                else:
                    c[i] = d[i] * e[i] + 1.0
            else:
                b[i] = a[i] + e[i] * e[i]
                if x[0] > 0.0:
                    c[i] = a[i] + d[i] * d[i]
                else:
                    c[i] = c[i] + e[i] * e[i]


@dace.program
def dace_s2711(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], c: dace.float64[LEN_1D]
):
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D):
            if b[i] != 0.0:
                a[i] = a[i] + b[i] * c[i]


@dace.program
def dace_s2712(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], c: dace.float64[LEN_1D]
):
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D):
            if a[i] > b[i]:
                a[i] = a[i] + b[i] * c[i]


# ==========================================================================
#  %2.8  Wrap-around / crossing
# ==========================================================================


@dace.program
def dace_s281(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], c: dace.float64[LEN_1D]
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            x = a[LEN_1D - i - 1] + b[i] * c[i]
            a[i] = x - 1.0
            b[i] = x


@dace.program
def dace_s1281(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D):
            x = (b[i] * c[i]) + (a[i] * d[i]) + e[i]
            a[i] = x - 1.0
            b[i] = x


# ==========================================================================
#  %2.9  Wrap-around variables
# ==========================================================================


@dace.program
def dace_s291(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(2 * ITERATIONS):
        a[0] = (b[0] + b[LEN_1D - 1]) * 0.5
        for i in range(1, LEN_1D):
            a[i] = (b[i] + b[i - 1]) * 0.5


@dace.program
def dace_s292(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(ITERATIONS):
        a[0] = (b[0] + b[LEN_1D - 1] + b[LEN_1D - 2]) * 0.333
        a[1] = (b[1] + b[0] + b[LEN_1D - 1]) * 0.333
        for i in range(2, LEN_1D):
            a[i] = (b[i] + b[i - 1] + b[i - 2]) * 0.333


@dace.program
def dace_s293(a: dace.float64[LEN_1D]):
    a0 = a[0]
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D):
            a[i] = a0


# ==========================================================================
#  %2.10  Diagonal / identity
# ==========================================================================


@dace.program
def dace_s2101(
    aa: dace.float64[LEN_2D, LEN_2D],
    bb: dace.float64[LEN_2D, LEN_2D],
    cc: dace.float64[LEN_2D, LEN_2D],
):
    for nl in range(1):
        for i in range(LEN_2D):
            aa[i, i] = aa[i, i] + bb[i, i] * cc[i, i]


@dace.program
def dace_s2102(aa: dace.float64[LEN_2D, LEN_2D]):
    for nl in range(100 * (ITERATIONS // LEN_2D)):
        for i in range(LEN_2D):
            for j in range(LEN_2D):
                aa[j, i] = 0.0
            aa[i, i] = 1.0


@dace.program
def dace_s2111(aa: dace.float64[LEN_2D, LEN_2D]):
    for nl in range(100 * (ITERATIONS // LEN_2D)):
        for j in range(1, LEN_2D):
            for i in range(1, LEN_2D):
                aa[j, i] = (aa[j, i - 1] + aa[j - 1, i]) / 1.9


# ==========================================================================
#  %3.1  Reductions
# ==========================================================================


@dace.program
def dace_s311(a: dace.float64[LEN_1D], sum_out: dace.float64[LEN_1D]):
    for nl in range(ITERATIONS * 10):
        sum_out[0] = 0.0
        for i in range(LEN_1D):
            sum_out[0] = sum_out[0] + a[i]


@dace.program
def dace_s31111(a: dace.float64[LEN_1D], b: dace.float64[2]):
    for nl in range(2000 * ITERATIONS):
        sum_val = 0.0
        for base in range(0, LEN_1D, 4):
            partial = 0.0
            partial = partial + a[base + 0]
            partial = partial + a[base + 1]
            partial = partial + a[base + 2]
            partial = partial + a[base + 3]
            sum_val = sum_val + partial
        b[0] = sum_val


@dace.program
def dace_s312(a: dace.float64[LEN_1D], result: dace.float64[1]):
    for nl in range(10 * ITERATIONS):
        prod = 1.0
        for i in range(LEN_1D):
            prod = prod * a[i]
    result[0] = prod


@dace.program
def dace_s313(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], dot: dace.float64[1]
):
    for nl in range(10 * ITERATIONS):
        dot[0] = 0.0
        for i in range(LEN_1D):
            dot[0] = dot[0] + a[i] * b[i]


@dace.program
def dace_s314(a: dace.float64[LEN_1D], result: dace.float64[1]):
    for nl in range(ITERATIONS):
        x = a[0]
        for i in range(1, LEN_1D):
            if a[i] > x:
                x = a[i]
    result[0] = x


@dace.program
def dace_s315(a: dace.float64[LEN_1D], result: dace.float64[1]):
    for i in range(LEN_1D):
        a[i] = float((i * 7) % LEN_1D)
    for nl in range(ITERATIONS):
        x = a[0]
        index = 0
        for i in range(LEN_1D):
            if a[i] > x:
                x = a[i]
                index = i
        a[0] = x + float(index)
    result[0] = a[0]


@dace.program
def dace_s316(a: dace.float64[LEN_1D], result: dace.float64[1]):
    for nl in range(ITERATIONS):
        x = a[0]
        for i in range(1, LEN_1D):
            if a[i] < x:
                x = a[i]
    result[0] = x


@dace.program
def dace_s317(q: dace.float64[LEN_1D]):
    for nl in range(5 * ITERATIONS):
        q[0] = 1.0
        for i in range(LEN_1D // 2):
            q[0] = q[0] * 0.99


@dace.program
def dace_s318(a: dace.float64[LEN_1D], result: dace.float64[1], inc: dace.int32):
    for nl in range(ITERATIONS // 2):
        k = 0
        index = 0
        maxv = abs(a[0])
        k = k + inc
        for i in range(1, LEN_1D):
            v = abs(a[k])
            if v > maxv:
                index = i
                maxv = v
            k = k + inc
        result[0] = maxv + float(index)


@dace.program
def dace_s319(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(2 * ITERATIONS):
        sum_val = 0.0
        for i in range(LEN_1D):
            a[i] = c[i] + d[i]
            sum_val = sum_val + a[i]
            b[i] = c[i] + e[i]
            sum_val = sum_val + b[i]
        b[0] = sum_val


@dace.program
def dace_s3110(aa: dace.float64[LEN_2D, LEN_2D], bb: dace.float64[2, 2]):
    for nl in range(100 * (ITERATIONS // LEN_2D)):
        maxv = aa[0, 0]
        xindex = 0
        yindex = 0
        for i in range(LEN_2D):
            for j in range(LEN_2D):
                if aa[i, j] > maxv:
                    maxv = aa[i, j]
                    xindex = i
                    yindex = j
        chksum = maxv + float(xindex) + float(yindex)
        tmp = chksum
        tmp = tmp
        bb[0, 0] = chksum


@dace.program
def dace_s13110(aa: dace.float64[LEN_2D, LEN_2D], bb: dace.float64[2, 2]):
    for nl in range(100 * (ITERATIONS // LEN_2D)):
        maxv = aa[0, 0]
        xindex = 0
        yindex = 0
        for i in range(LEN_2D):
            for j in range(LEN_2D):
                if aa[i, j] > maxv:
                    maxv = aa[i, j]
                    xindex = i
                    yindex = j
        chksum = maxv + float(xindex) + float(yindex)
        tmp = chksum
        tmp = tmp
        bb[0, 0] = chksum


@dace.program
def dace_s3111(a: dace.float64[LEN_1D], b: dace.float64[2]):
    for nl in range(ITERATIONS // 2):
        sum_val = 0.0
        for i in range(LEN_1D):
            if a[i] > 0.0:
                sum_val = sum_val + a[i]
        b[0] = sum_val


@dace.program
def dace_s3112(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(ITERATIONS):
        sum = 0.0
        for i in range(LEN_1D):
            sum = sum + a[i]
            b[i] = sum


@dace.program
def dace_s3113(a: dace.float64[LEN_1D], b: dace.float64[2]):
    maxv = dace.float64(0)
    for nl in range(ITERATIONS * 4):
        maxv = abs(a[0])
        for i in range(LEN_1D):
            av = abs(a[i])
            if av > maxv:
                maxv = av
    b[0] = maxv


# ==========================================================================
#  %3.2  Recurrences
# ==========================================================================


@dace.program
def dace_s321(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(ITERATIONS):
        for i in range(1, LEN_1D):
            a[i] = a[i] + a[i - 1] * b[i]


@dace.program
def dace_s322(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], c: dace.float64[LEN_1D]
):
    for nl in range(ITERATIONS // 2):
        for i in range(2, LEN_1D):
            a[i] = a[i] + a[i - 1] * b[i] + a[i - 2] * c[i]


@dace.program
def dace_s323(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS // 2):
        for i in range(1, LEN_1D):
            a[i] = b[i - 1] + c[i] * d[i]
            b[i] = a[i] + c[i] * e[i]


# ==========================================================================
#  %3.3  Search loops
# ==========================================================================


@dace.program
def dace_s331(a: dace.float64[LEN_1D], b: dace.float64[2]):
    j = -1
    for nl in range(ITERATIONS):
        j = -1
        for i in range(LEN_1D):
            if a[i] < 0.0:
                j = i
    b[0] = j


@dace.program
def dace_s332(a: dace.float64[LEN_1D], result: dace.float64[1], threshold: dace.int64):
    for nl in range(ITERATIONS):
        index = -2
        value = -1.0
        for i in range(LEN_1D):
            if a[i] > threshold:
                index = i
                value = a[i]
                break
        result[0] = value + float(index)


# ==========================================================================
#  %3.4  Packing
# ==========================================================================


@dace.program
def dace_s341(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(ITERATIONS):
        j = -1
        for i in range(LEN_1D):
            if b[i] > 0.0:
                j = j + 1
                a[j] = b[i]


@dace.program
def dace_s342(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(ITERATIONS):
        j = -1
        for i in range(LEN_1D):
            if a[i] > 0.0:
                j = j + 1
                a[i] = b[j]


@dace.program
def dace_s343(
    aa: dace.float64[LEN_2D, LEN_2D],
    bb: dace.float64[LEN_2D, LEN_2D],
    flat_2d_array: dace.float64[LEN_2D * LEN_2D],
):
    for nl in range(10 * (ITERATIONS // LEN_2D)):
        k = -1
        for i in range(LEN_2D):
            for j in range(LEN_2D):
                if bb[j, i] > 0.0:
                    k = k + 1
                    flat_2d_array[k] = aa[j, i]


# ==========================================================================
#  %3.5  Loop rerolling
# ==========================================================================


@dace.program
def dace_s351(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], c: dace.float64[LEN_1D]
):
    alpha = c[0]
    for nl in range(8 * ITERATIONS):
        for i in range(0, LEN_1D, 4):
            a[i] = a[i] + alpha * b[i]
            a[i + 1] = a[i + 1] + alpha * b[i + 1]
            a[i + 2] = a[i + 2] + alpha * b[i + 2]
            a[i + 3] = a[i + 3] + alpha * b[i + 3]


@dace.program
def dace_s1351(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], c: dace.float64[LEN_1D]
):
    for nl in range(8 * ITERATIONS):
        for i in range(LEN_1D):
            a[i] = b[i] + c[i]


@dace.program
def dace_s352(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], c: dace.float64[2]):
    dot = 0.0
    for nl in range(8 * ITERATIONS):
        dot = 0.0
        for i in range(0, LEN_1D, 4):
            dot = dot + (
                a[i] * b[i]
                + a[i + 1] * b[i + 1]
                + a[i + 2] * b[i + 2]
                + a[i + 3] * b[i + 3]
                + a[i + 4] * b[i + 4]
            )
    c[0] = dot


@dace.program
def dace_s353(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    ip: dace.int32[LEN_1D],
):
    alpha = c[0]
    for nl in range(ITERATIONS):
        for i in range(0, LEN_1D, 4):
            a[i] = a[i] + alpha * b[ip[i]]
            a[i + 1] = a[i + 1] + alpha * b[ip[i + 1]]
            a[i + 2] = a[i + 2] + alpha * b[ip[i + 2]]
            a[i + 3] = a[i + 3] + alpha * b[ip[i + 3]]


# ==========================================================================
#  %4.1–4.2  Storage classes / aliasing
# ==========================================================================


@dace.program
def dace_s421(a: dace.float64[LEN_1D], flat_2d_array: dace.float64[LEN_1D]):
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D - 1):
            flat_2d_array[i] = flat_2d_array[i + 1] + a[i]


@dace.program
def dace_s1421(b: dace.float64[LEN_1D], a: dace.float64[LEN_1D]):
    half = LEN_1D // 2
    for nl in range(8 * ITERATIONS):
        for i in range(half):
            b[i] = b[half + i] + a[i]


@dace.program
def dace_s422(a: dace.float64[LEN_1D], flat_2d_array: dace.float64[LEN_1D * LEN_1D]):
    for nl in range(8 * ITERATIONS):
        for i in range(LEN_1D):
            flat_2d_array[4 + i] = flat_2d_array[8 + i] + a[i]


@dace.program
def dace_s423(a: dace.float64[LEN_1D], flat_2d_array: dace.float64[LEN_1D]):
    vl = 64
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D - 1):
            flat_2d_array[i + 1] = flat_2d_array[vl + i] + a[i]


@dace.program
def dace_s424(
    a: dace.float64[LEN_1D], xx: dace.float64[LEN_1D], flat: dace.float64[LEN_1D]
):
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D - 1):
            xx[i + 1] = flat[i] + a[i]


# ==========================================================================
#  %4.3  Parameters / constants
# ==========================================================================


@dace.program
def dace_s431(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(ITERATIONS * 10):
        for i in range(LEN_1D):
            a[i] = a[i] + b[i]


# ==========================================================================
#  %4.4  Non-logical if's
# ==========================================================================


@dace.program
def dace_s441(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            if d[i] < 0.0:
                a[i] = a[i] + b[i] * c[i]
            elif d[i] == 0.0:
                a[i] = a[i] + b[i] * b[i]
            else:
                a[i] = a[i] + c[i] * c[i]


@dace.program
def dace_s442(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
    indx: dace.int32[LEN_1D],
):
    for nl in range(ITERATIONS // 2):
        for i in range(LEN_1D):
            if indx[i] == 1:
                a[i] = a[i] + (b[i] * b[i])
            elif indx[i] == 2:
                a[i] = a[i] + (c[i] * c[i])
            elif indx[i] == 3:
                a[i] = a[i] + (d[i] * d[i])
            elif indx[i] == 4:
                a[i] = a[i] + (e[i] * e[i])


@dace.program
def dace_s443(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
):
    for nl in range(2 * ITERATIONS):
        for i in range(LEN_1D):
            if d[i] <= 0.0:
                a[i] = a[i] + b[i] * c[i]
            else:
                a[i] = a[i] + b[i] * b[i]


# ==========================================================================
#  %4.5  Intrinsics / type conversion
# ==========================================================================


@dace.program
def dace_s451(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], c: dace.float64[LEN_1D]
):
    for nl in range(ITERATIONS // 5):
        for i in range(LEN_1D):
            a[i] = sin(b[i]) + cos(c[i])


@dace.program
def dace_s452(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], c: dace.float64[LEN_1D]
):
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D):
            a[i] = b[i] + c[i] * (i + 1)


@dace.program
def dace_s453(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(ITERATIONS * 2):
        s = 0.0
        for i in range(LEN_1D):
            s = s + 2.0
            a[i] = s * b[i]


# ==========================================================================
#  %4.7  Statement functions / calls
# ==========================================================================


@dace.program
def dace_s471(
    x: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    e: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS // 2):
        for i in range(LEN_1D):
            x[i] = b[i] + d[i] * d[i]
            b[i] = c[i] + d[i] * e[i]


# ==========================================================================
#  %4.8  Early loop exit
# ==========================================================================


@dace.program
def dace_s481(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            if d[i] < 0.0:
                break
            a[i] = a[i] + b[i] * c[i]


@dace.program
def dace_s482(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], c: dace.float64[LEN_1D]
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            a[i] = a[i] + b[i] * c[i]
            if c[i] > b[i]:
                break


# ==========================================================================
#  %4.9  Indirect addressing
# ==========================================================================


@dace.program
def dace_s491(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
    ip: dace.int32[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            a[ip[i]] = b[i] + c[i] * d[i]


@dace.program
def dace_s4112(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], ip: dace.int32[LEN_1D]
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            a[i] = a[i] + b[ip[i]] * 2.0


@dace.program
def dace_s4113(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    ip: dace.int32[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            a[ip[i]] = b[ip[i]] + c[i]


@dace.program
def dace_s4114(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d_: dace.float64[LEN_1D],
    ip: dace.int32[LEN_1D],
    n1: dace.int32,
):
    for nl in range(ITERATIONS):
        for i in range(n1 - 1, LEN_1D):
            k = ip[i]
            a[i] = b[i] + c[LEN_1D - k - 1] * d_[i]


@dace.program
def dace_s4115(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    ip: dace.int32[LEN_1D],
    sum_out: dace.float64[1],
):
    sum_val = 0.0
    for nl in range(ITERATIONS):
        sum_val = 0.0
        for i in range(LEN_1D):
            sum_val = sum_val + a[i] * b[ip[i]]
    sum_out[0] = sum_val


@dace.program
def dace_s4116(
    a: dace.float64[LEN_1D],
    aa: dace.float64[LEN_2D, LEN_2D],
    ip: dace.int32[LEN_2D],
    j: dace.int32,
    inc: dace.int32,
    sum_out: dace.float64[1],
):
    sum_val = 0.0
    for nl in range(100 * ITERATIONS):
        sum_val = 0.0
        for i in range(LEN_2D - 1):
            off = inc + i
            sum_val = sum_val + a[off] * aa[j - 1, ip[i]]
    sum_out[0] = sum_val


@dace.program
def dace_s4117(
    a: dace.float64[LEN_1D],
    b: dace.float64[LEN_1D],
    c: dace.float64[LEN_1D],
    d: dace.float64[LEN_1D],
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            j = i // 2
            a[i] = b[i] + c[j] * d[i]


# ==========================================================================
#  %4.12  Statement functions
# ==========================================================================


@dace.program
def dace_s4121(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], c: dace.float64[LEN_1D]
):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            a[i] = a[i] + b[i] * c[i]


# ==========================================================================
#  %5  Vector operations
# ==========================================================================


@dace.program
def dace_va(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(ITERATIONS * 10):
        for i in range(LEN_1D):
            a[i] = b[i]


@dace.program
def dace_vag(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], ip: dace.int32[LEN_1D]):
    for nl in range(2 * ITERATIONS):
        for i in range(LEN_1D):
            a[i] = b[ip[i]]


@dace.program
def dace_vas(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], ip: dace.int32[LEN_1D]):
    for nl in range(2 * ITERATIONS):
        for i in range(LEN_1D):
            a[ip[i]] = b[i]


@dace.program
def dace_vif(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            if b[i] > 0.0:
                a[i] = b[i]


@dace.program
def dace_vpv(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(ITERATIONS * 10):
        for i in range(LEN_1D):
            a[i] = a[i] + b[i]


@dace.program
def dace_vtv(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(ITERATIONS * 10):
        for i in range(LEN_1D):
            a[i] = a[i] * b[i]


@dace.program
def dace_vpvtv(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], c: dace.float64[LEN_1D]
):
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D):
            a[i] = a[i] + b[i] * c[i]


@dace.program
def dace_vpvts(a: dace.float64[LEN_1D], b: dace.float64[LEN_1D]):
    for nl in range(ITERATIONS):
        for i in range(LEN_1D):
            a[i] = a[i] + b[i] * S


@dace.program
def dace_vpvpv(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], c: dace.float64[LEN_1D]
):
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D):
            a[i] = a[i] + b[i] + c[i]


@dace.program
def dace_vtvtv(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], c: dace.float64[LEN_1D]
):
    for nl in range(4 * ITERATIONS):
        for i in range(LEN_1D):
            a[i] = a[i] * b[i] * c[i]


@dace.program
def dace_vsumr(a: dace.float64[LEN_1D], sum_out: dace.float64[1]):
    s = 0.0
    for nl in range(ITERATIONS * 10):
        s = 0.0
        for i in range(LEN_1D):
            s = s + a[i]
    sum_out[0] = s


@dace.program
def dace_vdotr(
    a: dace.float64[LEN_1D], b: dace.float64[LEN_1D], dot_out: dace.float64[LEN_1D]
):
    dot_out[0] = 0.0
    for nl in range(ITERATIONS * 10):
        dot_out[0] = 0.0
        for i in range(LEN_1D):
            dot_out[0] = dot_out[0] + a[i] * b[i]


@dace.program
def dace_vbor(
    a: dace.float64[LEN_2D],
    b: dace.float64[LEN_2D],
    c: dace.float64[LEN_2D],
    d: dace.float64[LEN_2D],
    e: dace.float64[LEN_2D],
    x: dace.float64[LEN_2D],
):
    for nl in range(ITERATIONS * 10):
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
