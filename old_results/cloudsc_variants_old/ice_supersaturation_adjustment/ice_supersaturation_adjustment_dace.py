"""DaCe Python-frontend version of ``ice_supersaturation_adjustment``."""
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
        zsolqa: dace.float64[KLON, NCLV, NCLV], zsolac: dace.float64[KLON],
        zqxfg: dace.float64[KLON, NCLV],
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
                zsolqa[jl, NCLDQL - 1, NCLDQV - 1] = zsolqa[jl, NCLDQL - 1, NCLDQV - 1] + zsupsat
                zsolqa[jl, NCLDQV - 1, NCLDQL - 1] = zsolqa[jl, NCLDQV - 1, NCLDQL - 1] - zsupsat
                zqxfg[jl, NCLDQL - 1] = zqxfg[jl, NCLDQL - 1] + zsupsat
            else:
                zsolqa[jl, NCLDQI - 1, NCLDQV - 1] = zsolqa[jl, NCLDQI - 1, NCLDQV - 1] + zsupsat
                zsolqa[jl, NCLDQV - 1, NCLDQI - 1] = zsolqa[jl, NCLDQV - 1, NCLDQI - 1] - zsupsat
                zqxfg[jl, NCLDQI - 1] = zqxfg[jl, NCLDQI - 1] + zsupsat
            zsolac[jl] = (1.0 - za[jl]) * zfaci
