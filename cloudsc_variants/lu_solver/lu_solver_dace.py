"""DaCe Python-frontend version of ``lu_solver_microphysics``.

Array axes are declared **reversed** relative to the Fortran source
(``ZQLHS(JL,JM,JN)`` -> ``zqlhs[jn, jm, jl]``, shape ``[NCLV, NCLV, KLON]``
instead of ``[KLON, NCLV, NCLV]``) -- this is deliberate, not a typo.

The original 1:1 port kept the same index *order* as the Fortran declaration
(``zqlhs[jl, jm, jn]``, shape ``[KLON, NCLV, NCLV]``), but Fortran arrays are
column-major (first-declared axis is fastest/unit-stride) while DaCe's
default storage for this array is row-major/C-order (last axis is
fastest/unit-stride). Keeping the same index order across that storage-order
switch silently transposes the physical layout: ``JL`` was the fast axis in
Fortran, but ``jl`` became the *slowest* axis (stride ``NCLV**2``, a runtime
value) in the generated C++ -- which is exactly what defeated clang's
auto-vectorizer on this loop nest (LLVM cannot prove a runtime, non-unit
stride is safe to vectorize, even though the per-column LU systems are
genuinely independent).

Reversing every index tuple (the standard C-order/F-order transpose trick --
identical to what ``array.transpose()`` does to reinterpret a C-order array
as its byte-identical F-order counterpart of reversed shape) puts ``jl`` back
at unit stride under DaCe's ordinary default C-contiguous storage, matching
what the Fortran-frontend gets for free from Fortran's native column-major
layout -- no custom strides, no pragma, no generated-code hacking needed.

Callers must hand this program arrays laid out ``[NCLV, NCLV, KLON]`` /
``[NCLV, KLON]`` accordingly -- see ``run_lu_solver.py``'s ``make_live`` /
``refresh_live`` / ``extract_out`` hooks, which transpose to/from the
canonical ``[KLON, NCLV, NCLV]`` / ``[KLON, NCLV]`` shape used by the NumPy
oracle, the original Fortran lane, and the Fortran-frontend SDFG.
"""
import dace

KLON = dace.symbol("KLON")
NCLV = dace.symbol("NCLV")


@dace.program
def lu_solver_microphysics(zqlhs: dace.float64[NCLV, NCLV, KLON],
                           zqxn: dace.float64[NCLV, KLON]):
    for jn in range(0, NCLV - 1):
        for jm in range(jn + 1, NCLV):
            for jl in range(0, KLON):
                zqlhs[jn, jm, jl] = zqlhs[jn, jm, jl] / zqlhs[jn, jn, jl]
            for ik in range(jn + 1, NCLV):
                for jl in range(0, KLON):
                    zqlhs[ik, jm, jl] = zqlhs[ik, jm, jl] - (zqlhs[jn, jm, jl] * zqlhs[ik, jn, jl])

    for jn in range(1, NCLV):
        for jm in range(0, jn):
            for jl in range(0, KLON):
                zqxn[jn, jl] = zqxn[jn, jl] - (zqlhs[jm, jn, jl] * zqxn[jm, jl])

    for jl in range(0, KLON):
        zqxn[NCLV - 1, jl] = zqxn[NCLV - 1, jl] / zqlhs[NCLV - 1, NCLV - 1, jl]

    for jn in range(NCLV - 2, -1, -1):
        for jm in range(jn + 1, NCLV):
            for jl in range(0, KLON):
                zqxn[jn, jl] = zqxn[jn, jl] - (zqlhs[jm, jn, jl] * zqxn[jm, jl])
        for jl in range(0, KLON):
            zqxn[jn, jl] = zqxn[jn, jl] / zqlhs[jn, jn, jl]
