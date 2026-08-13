"""DaCe Python-frontend version of ``autoconversion_snow``.

Same body as ``autoconversion_snow_numpy.py`` but decorated with
``@dace.program`` and dace-typed so ``.to_sdfg()`` produces the
Python-frontend SDFG. Symbols KLON/NCLDQS/NCLDQI are dace symbols;
scalars are passed by value.

The one multi-dimensional array (``zsolqb``) is declared **axis reversed**
relative to the Fortran source (``zsolqb[jl, a, b]`` -> ``zsolqb[b, a, jl]``,
shape ``[NCLDQI, NCLDQS, KLON]`` instead of ``[KLON, NCLDQS, NCLDQI]``) --
deliberate, not a typo. See ``lu_solver_dace.py``'s module docstring for the
full explanation. Every other array here is 1-D (``[KLON]``) and needs no
change.

Callers must hand this program ``zsolqb`` laid out ``[NCLDQI, NCLDQS,
KLON]`` -- see ``run_autoconversion_snow.py``'s ``make_live`` /
``refresh_live`` / ``extract_out`` hooks, which transpose to/from the
canonical ``[KLON, NCLDQS, NCLDQI]`` shape used by the NumPy oracle, the
original Fortran lane, and the Fortran-frontend SDFG.
"""
import dace
import numpy as np

KLON = dace.symbol("KLON")
NCLDQS = dace.symbol("NCLDQS")
NCLDQI = dace.symbol("NCLDQI")


@dace.program
def autoconversion_snow(ztp1: dace.float64[KLON], zicecld: dace.float64[KLON],
                        pnice: dace.float64[KLON],
                        zsolqb: dace.float64[NCLDQI, NCLDQS, KLON],
                        zsnowaut: dace.float64[KLON],
                        rtt: dace.float64, rlcritsnow: dace.float64,
                        rsnowlin1: dace.float64, rsnowlin2: dace.float64,
                        rnice: dace.float64, ptsphy: dace.float64,
                        zepsec: dace.float64, laericeauto: dace.int64):
    for jl in range(0, KLON):
        zsnowaut[jl] = 0.0

    for jl in range(0, KLON):
        if ztp1[jl] <= rtt:
            if zicecld[jl] > zepsec:
                zzco = ptsphy * rsnowlin1 * np.exp(rsnowlin2 * (ztp1[jl] - rtt))
                if laericeauto != 0:
                    zlcrit = rlcritsnow
                    zzco = zzco * (rnice / pnice[jl]) ** 0.333
                else:
                    zlcrit = rlcritsnow
                zsnowaut[jl] = zzco * (1.0 - np.exp(-(zicecld[jl] / zlcrit) ** 2))
                zsolqb[NCLDQI - 1, NCLDQS - 1, jl] = \
                    zsolqb[NCLDQI - 1, NCLDQS - 1, jl] + zsnowaut[jl]
