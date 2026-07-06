"""Manual NumPy port of the CloudSC ``autoconversion_snow`` loop nest.

Faithful, explicit-loop transcription of
``cloudsc_loopnests/autoconversion_snow.f90`` (1-based Fortran indices
shifted to 0-based; ``ZSOLQB(JL,NCLDQS,NCLDQI)`` -> the last (NCLDQS-1,
NCLDQI-1) slot). Outputs ``zsnowaut`` and ``zsolqb`` are mutated in
place. This single file is BOTH the numerical oracle and the source the
NumpyToX translators (C / C++ / Fortran) ingest, so the body stays inside
the supported numeric subset (explicit ``for``/``if``, ``np.exp``,
``**``).
"""
import numpy as np


def autoconversion_snow(ztp1, zicecld, pnice, zsolqb, zsnowaut,
                        rtt, rlcritsnow, rsnowlin1, rsnowlin2, rnice,
                        ptsphy, zepsec, laericeauto, KLON, NCLDQS, NCLDQI):
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
                zsolqb[jl, NCLDQS - 1, NCLDQI - 1] = \
                    zsolqb[jl, NCLDQS - 1, NCLDQI - 1] + zsnowaut[jl]
