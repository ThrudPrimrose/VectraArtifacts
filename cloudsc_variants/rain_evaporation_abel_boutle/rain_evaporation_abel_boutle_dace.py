"""DaCe Python-frontend version of ``rain_evaporation_abel_boutle``.

The one multi-dimensional array (``zsolqa``) is declared **axis reversed**
relative to the Fortran source (``zsolqa[jl, a, b]`` -> ``zsolqa[b, a, jl]``,
shape ``[NCLV, NCLV, KLON]`` instead of ``[KLON, NCLV, NCLV]``) -- deliberate,
not a typo. See ``lu_solver_dace.py``'s module docstring for the full
explanation. Every other array here is 1-D (``[KLON]``) and needs no change.

Callers must hand this program ``zsolqa`` laid out ``[NCLV, NCLV, KLON]`` --
see ``run_rain_evaporation_abel_boutle.py``'s ``make_live`` / ``refresh_live``
/ ``extract_out`` hooks, which transpose to/from the canonical
``[KLON, NCLV, NCLV]`` shape used by the NumPy oracle, the original Fortran
lane, and the Fortran-frontend SDFG.
"""
import dace
import numpy as np

KLON = dace.symbol("KLON")
NCLV = dace.symbol("NCLV")
NCLDQV = dace.symbol("NCLDQV")
NCLDQR = dace.symbol("NCLDQR")


@dace.program
def rain_evaporation_abel_boutle(
        ztp1: dace.float64[KLON], zqx_ncldqv: dace.float64[KLON], za: dace.float64[KLON],
        zqsliq: dace.float64[KLON], zqxfg_ncldqr: dace.float64[KLON],
        zcovptot: dace.float64[KLON], zcovpclr: dace.float64[KLON],
        zcovpmax: dace.float64[KLON], zrho: dace.float64[KLON], pap: dace.float64[KLON],
        zsolqa: dace.float64[NCLV, NCLV, KLON], zevap_out: dace.float64[KLON],
        rtt: dace.float64, rv: dace.float64, rd: dace.float64, rprecrhmax: dace.float64,
        rcovpmin: dace.float64, rdensref: dace.float64, ptsphy: dace.float64, zepsec: dace.float64,
        rcl_fac1: dace.float64, rcl_fac2: dace.float64, rcl_cdenom1: dace.float64,
        rcl_cdenom2: dace.float64, rcl_cdenom3: dace.float64, rcl_ka273: dace.float64,
        rcl_const1r: dace.float64, rcl_const2r: dace.float64, rcl_const3r: dace.float64,
        rcl_const4r: dace.float64):
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

            zsolqa[NCLDQR - 1, NCLDQV - 1, jl] = zsolqa[NCLDQR - 1, NCLDQV - 1, jl] + zevap
            zsolqa[NCLDQV - 1, NCLDQR - 1, jl] = zsolqa[NCLDQV - 1, NCLDQR - 1, jl] - zevap

            zcovptot[jl] = max(rcovpmin, zcovptot[jl] - max(0.0,
                               (zcovptot[jl] - za[jl]) * zevap / zqxfg_ncldqr[jl]))

            zqxfg_ncldqr[jl] = zqxfg_ncldqr[jl] - zevap
