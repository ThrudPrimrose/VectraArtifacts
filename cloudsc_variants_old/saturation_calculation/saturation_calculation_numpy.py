"""Manual NumPy port of the CloudSC ``compute_saturation_values`` loop nest.

Explicit-loop transcription of
``cloudsc_loopnests/saturation_calculation.f90`` (2-D over KLON x KLEV,
1-based -> 0-based). The Fortran ``MAX(0, SIGN(1, PTARE-RTT))`` FOEDELTA
is realised as ``if ptare >= rtt`` (identical: SIGN(1,0)=+1, so >=).
All seven ``Z*`` arrays are mutated outputs.
"""
import numpy as np


def compute_saturation_values(ztp1, pap, zfoealfa, zfoeewmt, zqsmix, zfoeew, zqsice,
                              zfoeeliqt, zqsliq,
                              rtt, retv, r2es, r3les, r3ies, r4les, r4ies, rtice, rtwat,
                              rtwat_rtice_r, KLON, KLEV):
    for jk in range(0, KLEV):
        for jl in range(0, KLON):
            ptare = ztp1[jl, jk]

            zfoealfa_loc = ((max(rtice, min(rtwat, ptare)) - rtice) * rtwat_rtice_r) ** 2
            zfoealfa_loc = min(1.0, zfoealfa_loc)
            zfoealfa[jl, jk] = zfoealfa_loc

            zfoeeliq_loc = r2es * np.exp(r3les * (ptare - rtt) / (ptare - r4les))
            zfoeeice_loc = r2es * np.exp(r3ies * (ptare - rtt) / (ptare - r4ies))

            zfoeewm_loc = r2es * (zfoealfa_loc * np.exp(r3les * (ptare - rtt) / (ptare - r4les))
                                  + (1.0 - zfoealfa_loc) * np.exp(r3ies * (ptare - rtt) / (ptare - r4ies)))

            zfoeewmt[jl, jk] = min(zfoeewm_loc / pap[jl, jk], 0.5)
            zqsmix[jl, jk] = zfoeewmt[jl, jk]
            zqsmix[jl, jk] = zqsmix[jl, jk] / (1.0 - retv * zqsmix[jl, jk])

            if ptare >= rtt:
                zdelta = 1.0
            else:
                zdelta = 0.0

            zfoeew[jl, jk] = (zdelta * zfoeeliq_loc + (1.0 - zdelta) * zfoeeice_loc) / pap[jl, jk]
            zfoeew[jl, jk] = min(0.5, zfoeew[jl, jk])
            zqsice[jl, jk] = zfoeew[jl, jk] / (1.0 - retv * zfoeew[jl, jk])

            zfoeeliqt[jl, jk] = min(zfoeeliq_loc / pap[jl, jk], 0.5)
            zqsliq[jl, jk] = zfoeeliqt[jl, jk]
            zqsliq[jl, jk] = zqsliq[jl, jk] / (1.0 - retv * zqsliq[jl, jk])
