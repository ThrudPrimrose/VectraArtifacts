"""DaCe Python-frontend version of ``ice_supersaturation_adjustment``.

The two multi-dimensional arrays (``zsolqa``, ``zqxfg``) are declared **axis
reversed** relative to the Fortran source (``zsolqa[jl, a, b]`` ->
``zsolqa[b, a, jl]``, shape ``[NCLV, NCLV, KLON]`` / ``[NCLV, KLON]`` instead
of ``[KLON, NCLV, NCLV]`` / ``[KLON, NCLV]``) -- deliberate, not a typo. See
``lu_solver_dace.py``'s module docstring for the full explanation. Every
other array here is 1-D (``[KLON]``) and needs no change: a single axis has
no row-major/column-major distinction to get wrong.

Note: on this kernel specifically, both frontends already fail to
auto-vectorize under clang (real branching in the loop body, not a stride
issue -- see the ``ice_supersaturation_adjustment`` vec_remarks comparison),
so this fix corrects the translation but is not expected to change
vectorization outcome here. Kept for correctness/consistency with the other
kernels regardless.

Callers must hand this program ``zsolqa``/``zqxfg`` laid out
``[NCLV, NCLV, KLON]`` / ``[NCLV, KLON]`` -- see
``run_ice_supersaturation_adjustment.py``'s ``make_live`` / ``refresh_live``
/ ``extract_out`` hooks, which transpose to/from the canonical
``[KLON, NCLV, NCLV]`` / ``[KLON, NCLV]`` shape used by the NumPy oracle, the
original Fortran lane, and the Fortran-frontend SDFG.
"""
import dace

KLON = dace.symbol("KLON")
NCLV = dace.symbol("NCLV")
NCLDQL = dace.symbol("NCLDQL")
NCLDQI = dace.symbol("NCLDQI")
NCLDQV = dace.symbol("NCLDQV")


@dace.program
def ice_supersaturation_adjustment(
        ztp1: dace.float64[KLON], za: dace.float64[KLON], zqx_ncldqv: dace.float64[KLON],
        zqsice: dace.float64[KLON], zcorqsice: dace.float64[KLON], zfokoop: dace.float64[KLON],
        zsolqa: dace.float64[NCLV, NCLV, KLON], zsolac: dace.float64[KLON],
        zqxfg: dace.float64[NCLV, KLON],
        rtt: dace.float64, ramin: dace.float64, rthomo: dace.float64,
        rkooptau: dace.float64, ptsphy: dace.float64, zepsec: dace.float64,
        nssopt: dace.int64):
    zepsilon = 1.0e-14
    for jl in range(0, KLON):
        if ztp1[jl] >= rtt or nssopt == 0:
            zfac = 1.0
            zfaci = 1.0
        else:
            zfac = za[jl] + zfokoop[jl] * (1.0 - za[jl])
            zfaci = ptsphy / rkooptau

        if za[jl] > 1.0 - ramin:
            zsupsat = max((zqx_ncldqv[jl] - zfac * zqsice[jl]) / zcorqsice[jl], 0.0)
        else:
            zqp1env = (zqx_ncldqv[jl] - za[jl] * zqsice[jl]) / max(1.0 - za[jl], zepsilon)
            zsupsat = max((1.0 - za[jl]) * (zqp1env - zfac * zqsice[jl]) / zcorqsice[jl], 0.0)

        if zsupsat > zepsec:
            if ztp1[jl] > rthomo:
                zsolqa[NCLDQV - 1, NCLDQL - 1, jl] = zsolqa[NCLDQV - 1, NCLDQL - 1, jl] + zsupsat
                zsolqa[NCLDQL - 1, NCLDQV - 1, jl] = zsolqa[NCLDQL - 1, NCLDQV - 1, jl] - zsupsat
                zqxfg[NCLDQL - 1, jl] = zqxfg[NCLDQL - 1, jl] + zsupsat
            else:
                zsolqa[NCLDQV - 1, NCLDQI - 1, jl] = zsolqa[NCLDQV - 1, NCLDQI - 1, jl] + zsupsat
                zsolqa[NCLDQI - 1, NCLDQV - 1, jl] = zsolqa[NCLDQI - 1, NCLDQV - 1, jl] - zsupsat
                zqxfg[NCLDQI - 1, jl] = zqxfg[NCLDQI - 1, jl] + zsupsat
            zsolac[jl] = (1.0 - za[jl]) * zfaci
