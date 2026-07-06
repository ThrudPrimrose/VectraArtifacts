! npbench-autogen -- generated from rain_evaporation_abel_boutle_numpy.py; edit the numpy reference and regenerate, or delete this line to keep local edits as a hand override.
subroutine rain_evaporation_abel_boutle_fp64(pap, za, zcovpclr, zcovpmax, zcovptot, zevap_out, zqsliq, zqx_ncldqv, zqxfg_ncldqr, zrho, zsolqa, ztp1, KLON, NCLDQR, NCLDQV, NCLV, ptsphy, rcl_cdenom1, rcl_cdenom2, rcl_cdenom3, rcl_const1r, rcl_const2r, rcl_const3r, rcl_const4r, rcl_fac1, rcl_fac2, rcl_ka273, rcovpmin, rd, rdensref, rprecrhmax, rtt, rv, zepsec, time_ns) bind(C, name="rain_evaporation_abel_boutle_fp64")
    use, intrinsic :: iso_c_binding
    integer(c_int64_t), value, intent(in) :: KLON
    integer(c_int64_t), value, intent(in) :: NCLDQR
    integer(c_int64_t), value, intent(in) :: NCLDQV
    integer(c_int64_t), value, intent(in) :: NCLV
    real(c_double), intent(in) :: pap(KLON)
    real(c_double), intent(in) :: za(KLON)
    real(c_double), intent(in) :: zcovpclr(KLON)
    real(c_double), intent(in) :: zcovpmax(KLON)
    real(c_double), intent(inout) :: zcovptot(KLON)
    real(c_double), intent(inout) :: zevap_out(KLON)
    real(c_double), intent(in) :: zqsliq(KLON)
    real(c_double), intent(in) :: zqx_ncldqv(KLON)
    real(c_double), intent(inout) :: zqxfg_ncldqr(KLON)
    real(c_double), intent(in) :: zrho(KLON)
    real(c_double), intent(inout) :: zsolqa(NCLV, NCLV, KLON)
    real(c_double), intent(in) :: ztp1(KLON)
    real(c_double), value, intent(in) :: ptsphy
    real(c_double), value, intent(in) :: rcl_cdenom1
    real(c_double), value, intent(in) :: rcl_cdenom2
    real(c_double), value, intent(in) :: rcl_cdenom3
    real(c_double), value, intent(in) :: rcl_const1r
    real(c_double), value, intent(in) :: rcl_const2r
    real(c_double), value, intent(in) :: rcl_const3r
    real(c_double), value, intent(in) :: rcl_const4r
    real(c_double), value, intent(in) :: rcl_fac1
    real(c_double), value, intent(in) :: rcl_fac2
    real(c_double), value, intent(in) :: rcl_ka273
    real(c_double), value, intent(in) :: rcovpmin
    real(c_double), value, intent(in) :: rd
    real(c_double), value, intent(in) :: rdensref
    real(c_double), value, intent(in) :: rprecrhmax
    real(c_double), value, intent(in) :: rtt
    real(c_double), value, intent(in) :: rv
    real(c_double), value, intent(in) :: zepsec
    integer(c_int64_t), intent(out) :: time_ns
    integer(c_int64_t) :: jl
    real(c_double) :: r2es_local
    real(c_double) :: r3les_local
    real(c_double) :: r4les_local
    real(c_double) :: zzrh
    real(c_double) :: zqe
    logical(c_bool) :: llo1
    real(c_double) :: zpreclr
    real(c_double) :: zfallcorr
    real(c_double) :: zesatliq
    real(c_double) :: zlambda
    real(c_double) :: zevap_denom
    real(c_double) :: zcorr2
    real(c_double) :: zka
    real(c_double) :: zsubsat
    real(c_double) :: zbeta
    real(c_double) :: zdenom
    real(c_double) :: zdpevap
    real(c_double) :: zevap
    integer(c_int64_t) :: t1_, t2_, rate_

    call system_clock(t1_, rate_)
    r2es_local = 611.21_c_double
    r3les_local = 17.502_c_double
    r4les_local = 32.19_c_double
    do jl = 0, (KLON) - 1
        zevap_out((jl) + 1) = 0.0_c_double
    end do
    do jl = 0, (KLON) - 1
        zzrh = (rprecrhmax + (((1.0_c_double - rprecrhmax) * zcovpmax((jl) + 1)) / max(zepsec, (1.0_c_double - za((jl) + 1)))))
        zzrh = min(max(zzrh, rprecrhmax), 1.0_c_double)
        zzrh = min(0.8_c_double, zzrh)
        zqe = max(0.0_c_double, min(zqx_ncldqv((jl) + 1), zqsliq((jl) + 1)))
        llo1 = ((zcovpclr((jl) + 1) > zepsec) .AND. (zqxfg_ncldqr((jl) + 1) > zepsec) .AND. (zqe < (zzrh * zqsliq((jl) + 1))))
        if (llo1) then
            zpreclr = (zqxfg_ncldqr((jl) + 1) / zcovptot((jl) + 1))
            zfallcorr = ((rdensref / zrho((jl) + 1)) ** 0.4_c_double)
            zesatliq = (((rv / rd) * r2es_local) * EXP(((r3les_local * (ztp1((jl) + 1) - rtt)) / (ztp1((jl) + 1) - r4les_local))))
            zlambda = ((rcl_fac1 / (zrho((jl) + 1) * zpreclr)) ** rcl_fac2)
            zevap_denom = (((rcl_cdenom1 * zesatliq) - ((rcl_cdenom2 * ztp1((jl) + 1)) * zesatliq)) + ((rcl_cdenom3 * (ztp1((jl) + 1) ** 3)) * pap((jl) + 1)))
            zcorr2 = ((((ztp1((jl) + 1) / 273.0_c_double) ** 1.5_c_double) * 393.0_c_double) / (ztp1((jl) + 1) + 120.0_c_double))
            zka = (rcl_ka273 * zcorr2)
            zsubsat = max(((zzrh * zqsliq((jl) + 1)) - zqe), 0.0_c_double)
            zbeta = ((((((0.5_c_double / zqsliq((jl) + 1)) * (ztp1((jl) + 1) ** 2)) * zesatliq) * rcl_const1r) * (zcorr2 / zevap_denom)) * ((0.78_c_double / (zlambda ** rcl_const4r)) + ((rcl_const2r * ((zrho((jl) + 1) * zfallcorr) ** 0.5_c_double)) / ((zcorr2 ** 0.5_c_double) * (zlambda ** rcl_const3r)))))
            zdenom = (1.0_c_double + (zbeta * ptsphy))
            zdpevap = ((((zcovpclr((jl) + 1) * zbeta) * ptsphy) * zsubsat) / zdenom)
            zevap = min(zdpevap, zqxfg_ncldqr((jl) + 1))
            zevap_out((jl) + 1) = zevap
            zsolqa(((NCLDQR - 1)) + 1, ((NCLDQV - 1)) + 1, (jl) + 1) = (zsolqa(((NCLDQR - 1)) + 1, ((NCLDQV - 1)) + 1, (jl) + 1) + zevap)
            zsolqa(((NCLDQV - 1)) + 1, ((NCLDQR - 1)) + 1, (jl) + 1) = (zsolqa(((NCLDQV - 1)) + 1, ((NCLDQR - 1)) + 1, (jl) + 1) - zevap)
            zcovptot((jl) + 1) = max(rcovpmin, (zcovptot((jl) + 1) - max(0.0_c_double, (((zcovptot((jl) + 1) - za((jl) + 1)) * zevap) / zqxfg_ncldqr((jl) + 1)))))
            zqxfg_ncldqr((jl) + 1) = (zqxfg_ncldqr((jl) + 1) - zevap)
        end if
    end do
    call system_clock(t2_)
    time_ns = (t2_ - t1_) * 1000000000_c_int64_t / rate_
end subroutine rain_evaporation_abel_boutle_fp64
