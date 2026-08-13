"""DaCe Python-frontend version of ``compute_saturation_values``.

Array axes are declared **reversed** relative to the Fortran source
(``ztp1[jl, jk]`` -> ``ztp1[jk, jl]``, shape ``[KLEV, KLON]`` instead of
``[KLON, KLEV]``), for every 2-D array here -- deliberate, not a typo. See
``lu_solver_dace.py``'s module docstring for the full explanation: keeping
the same index order as the Fortran declaration across the Fortran
(column-major) -> DaCe-default (row-major) storage switch silently
transposes the physical layout, leaving ``jl`` -- the embarrassingly-parallel
per-column dimension -- at a runtime, non-unit stride instead of stride 1.
Reversing every index tuple restores unit stride on ``jl`` under DaCe's
ordinary default C-contiguous storage.

Callers must hand this program arrays laid out ``[KLEV, KLON]`` -- see
``run_saturation_calculation.py``'s ``make_live`` / ``refresh_live`` /
``extract_out`` hooks, which transpose to/from the canonical ``[KLON, KLEV]``
shape used by the NumPy oracle, the original Fortran lane, and the
Fortran-frontend SDFG.
"""
import dace
import numpy as np

KLON = dace.symbol("KLON")
KLEV = dace.symbol("KLEV")


@dace.program
def compute_saturation_values(
        ztp1: dace.float64[KLEV, KLON], pap: dace.float64[KLEV, KLON],
        zfoealfa: dace.float64[KLEV, KLON], zfoeewmt: dace.float64[KLEV, KLON],
        zqsmix: dace.float64[KLEV, KLON], zfoeew: dace.float64[KLEV, KLON],
        zqsice: dace.float64[KLEV, KLON], zfoeeliqt: dace.float64[KLEV, KLON],
        zqsliq: dace.float64[KLEV, KLON],
        rtt: dace.float64, retv: dace.float64, r2es: dace.float64, r3les: dace.float64,
        r3ies: dace.float64, r4les: dace.float64, r4ies: dace.float64, rtice: dace.float64,
        rtwat: dace.float64, rtwat_rtice_r: dace.float64):
    for jk in range(0, KLEV):
        for jl in range(0, KLON):
            ptare = ztp1[jk, jl]

            zfoealfa_loc = ((max(rtice, min(rtwat, ptare)) - rtice) * rtwat_rtice_r) ** 2
            zfoealfa_loc = min(1.0, zfoealfa_loc)
            zfoealfa[jk, jl] = zfoealfa_loc

            zfoeeliq_loc = r2es * np.exp(r3les * (ptare - rtt) / (ptare - r4les))
            zfoeeice_loc = r2es * np.exp(r3ies * (ptare - rtt) / (ptare - r4ies))

            zfoeewm_loc = r2es * (zfoealfa_loc * np.exp(r3les * (ptare - rtt) / (ptare - r4les))
                                  + (1.0 - zfoealfa_loc) * np.exp(r3ies * (ptare - rtt) / (ptare - r4ies)))

            zfoeewmt[jk, jl] = min(zfoeewm_loc / pap[jk, jl], 0.5)
            zqsmix[jk, jl] = zfoeewmt[jk, jl]
            zqsmix[jk, jl] = zqsmix[jk, jl] / (1.0 - retv * zqsmix[jk, jl])

            if ptare >= rtt:
                zdelta = 1.0
            else:
                zdelta = 0.0

            zfoeew[jk, jl] = (zdelta * zfoeeliq_loc + (1.0 - zdelta) * zfoeeice_loc) / pap[jk, jl]
            zfoeew[jk, jl] = min(0.5, zfoeew[jk, jl])
            zqsice[jk, jl] = zfoeew[jk, jl] / (1.0 - retv * zfoeew[jk, jl])

            zfoeeliqt[jk, jl] = min(zfoeeliq_loc / pap[jk, jl], 0.5)
            zqsliq[jk, jl] = zfoeeliqt[jk, jl]
            zqsliq[jk, jl] = zqsliq[jk, jl] / (1.0 - retv * zqsliq[jk, jl])
