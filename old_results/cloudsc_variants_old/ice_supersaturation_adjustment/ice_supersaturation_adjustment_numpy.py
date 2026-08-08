"""Manual NumPy port of the CloudSC ``ice_supersaturation_adjustment`` loop nest.

Explicit-loop transcription of
``cloudsc_loopnests/ice_supersaturation_adjustment.f90`` (1-based -> 0-based;
the ``NCLDQx`` species indices are passed in 1-based and shifted at use).
Outputs ``zsolqa``, ``zsolac``, ``zqxfg`` are mutated in place.
"""


def ice_supersaturation_adjustment(ztp1, za, zqx_ncldqv, zqsice, zcorqsice, zfokoop,
                                   zsolqa, zsolac, zqxfg,
                                   rtt, ramin, rthomo, rkooptau, ptsphy, zepsec, nssopt,
                                   KLON, NCLV, NCLDQL, NCLDQI, NCLDQV):
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
