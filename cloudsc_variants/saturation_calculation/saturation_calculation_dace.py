"""DaCe Python-frontend version of ``compute_saturation_values``."""
import dace
import numpy as np

KLON = dace.symbol("KLON")
KLEV = dace.symbol("KLEV")


@dace.program
def compute_saturation_values(
        ztp1: dace.float64[KLON, KLEV], pap: dace.float64[KLON, KLEV],
        zfoealfa: dace.float64[KLON, KLEV], zfoeewmt: dace.float64[KLON, KLEV],
        zqsmix: dace.float64[KLON, KLEV], zfoeew: dace.float64[KLON, KLEV],
        zqsice: dace.float64[KLON, KLEV], zfoeeliqt: dace.float64[KLON, KLEV],
        zqsliq: dace.float64[KLON, KLEV],
        rtt: dace.float64, retv: dace.float64, r2es: dace.float64, r3les: dace.float64,
        r3ies: dace.float64, r4les: dace.float64, r4ies: dace.float64, rtice: dace.float64,
        rtwat: dace.float64, rtwat_rtice_r: dace.float64):
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
