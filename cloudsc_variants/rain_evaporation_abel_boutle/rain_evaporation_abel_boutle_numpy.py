"""Manual NumPy port of the CloudSC ``rain_evaporation_abel_boutle`` loop nest.

Explicit-loop transcription of
``cloudsc_loopnests/rain_evaporation_abel_boutle.f90`` (1-based -> 0-based;
species indices NCLDQV/NCLDQR passed 1-based, shifted at use). The
``LLO1`` Fortran LOGICAL is realised as a Python ``and`` chain. Outputs
``zqxfg_ncldqr``, ``zcovptot``, ``zsolqa``, ``zevap_out`` are mutated in
place.
"""
import numpy as np


def rain_evaporation_abel_boutle(
        ztp1, zqx_ncldqv, za, zqsliq, zqxfg_ncldqr, zcovptot, zcovpclr, zcovpmax,
        zrho, pap, zsolqa, zevap_out,
        rtt, rv, rd, rprecrhmax, rcovpmin, rdensref, ptsphy, zepsec,
        rcl_fac1, rcl_fac2, rcl_cdenom1, rcl_cdenom2, rcl_cdenom3,
        rcl_ka273, rcl_const1r, rcl_const2r, rcl_const3r, rcl_const4r,
        KLON, NCLV, NCLDQV, NCLDQR):
    r2es_local = 611.21
    r3les_local = 17.502
    r4les_local = 32.19

    for jl in range(0, KLON):
        zevap_out[jl] = 0.0

    for jl in range(0, KLON):
        zzrh = rprecrhmax + (1.0 - rprecrhmax) * zcovpmax[jl] / max(zepsec, 1.0 - za[jl])
        zzrh = min(max(zzrh, rprecrhmax), 1.0)
        zzrh = min(0.8, zzrh)

        zqe = max(0.0, min(zqx_ncldqv[jl], zqsliq[jl]))

        llo1 = (zcovpclr[jl] > zepsec) and (zqxfg_ncldqr[jl] > zepsec) and (zqe < zzrh * zqsliq[jl])

        if llo1:
            zpreclr = zqxfg_ncldqr[jl] / zcovptot[jl]
            zfallcorr = (rdensref / zrho[jl]) ** 0.4
            zesatliq = rv / rd * r2es_local * np.exp(r3les_local * (ztp1[jl] - rtt) / (ztp1[jl] - r4les_local))
            zlambda = (rcl_fac1 / (zrho[jl] * zpreclr)) ** rcl_fac2

            zevap_denom = (rcl_cdenom1 * zesatliq - rcl_cdenom2 * ztp1[jl] * zesatliq
                           + rcl_cdenom3 * ztp1[jl] ** 3 * pap[jl])
            zcorr2 = (ztp1[jl] / 273.0) ** 1.5 * 393.0 / (ztp1[jl] + 120.0)
            zka = rcl_ka273 * zcorr2

            zsubsat = max(zzrh * zqsliq[jl] - zqe, 0.0)

            zbeta = ((0.5 / zqsliq[jl]) * ztp1[jl] ** 2 * zesatliq
                     * rcl_const1r * (zcorr2 / zevap_denom)
                     * (0.78 / (zlambda ** rcl_const4r)
                        + rcl_const2r * (zrho[jl] * zfallcorr) ** 0.5
                        / (zcorr2 ** 0.5 * zlambda ** rcl_const3r)))

            zdenom = 1.0 + zbeta * ptsphy
            zdpevap = zcovpclr[jl] * zbeta * ptsphy * zsubsat / zdenom

            zevap = min(zdpevap, zqxfg_ncldqr[jl])
            zevap_out[jl] = zevap

            zsolqa[jl, NCLDQV - 1, NCLDQR - 1] = zsolqa[jl, NCLDQV - 1, NCLDQR - 1] + zevap
            zsolqa[jl, NCLDQR - 1, NCLDQV - 1] = zsolqa[jl, NCLDQR - 1, NCLDQV - 1] - zevap

            zcovptot[jl] = max(rcovpmin, zcovptot[jl] - max(0.0,
                               (zcovptot[jl] - za[jl]) * zevap / zqxfg_ncldqr[jl]))

            zqxfg_ncldqr[jl] = zqxfg_ncldqr[jl] - zevap
