! npbench-autogen -- generated from saturation_calculation_numpy.py; edit the numpy reference and regenerate, or delete this line to keep local edits as a hand override.
subroutine saturation_calculation_fp64(pap, zfoealfa, zfoeeliqt, zfoeew, zfoeewmt, zqsice, zqsliq, zqsmix, ztp1, KLEV, KLON, r2es, r3ies, r3les, r4ies, r4les, retv, rtice, rtt, rtwat, rtwat_rtice_r, time_ns) bind(C, name="saturation_calculation_fp64")
    use, intrinsic :: iso_c_binding
    integer(c_int64_t), value, intent(in) :: KLEV
    integer(c_int64_t), value, intent(in) :: KLON
    real(c_double), intent(in) :: pap(KLEV, KLON)
    real(c_double), intent(inout) :: zfoealfa(KLEV, KLON)
    real(c_double), intent(inout) :: zfoeeliqt(KLEV, KLON)
    real(c_double), intent(inout) :: zfoeew(KLEV, KLON)
    real(c_double), intent(inout) :: zfoeewmt(KLEV, KLON)
    real(c_double), intent(inout) :: zqsice(KLEV, KLON)
    real(c_double), intent(inout) :: zqsliq(KLEV, KLON)
    real(c_double), intent(inout) :: zqsmix(KLEV, KLON)
    real(c_double), intent(in) :: ztp1(KLEV, KLON)
    real(c_double), value, intent(in) :: r2es
    real(c_double), value, intent(in) :: r3ies
    real(c_double), value, intent(in) :: r3les
    real(c_double), value, intent(in) :: r4ies
    real(c_double), value, intent(in) :: r4les
    real(c_double), value, intent(in) :: retv
    real(c_double), value, intent(in) :: rtice
    real(c_double), value, intent(in) :: rtt
    real(c_double), value, intent(in) :: rtwat
    real(c_double), value, intent(in) :: rtwat_rtice_r
    integer(c_int64_t), intent(out) :: time_ns
    integer(c_int64_t) :: jk, jl
    real(c_double) :: ptare
    real(c_double) :: zfoealfa_loc
    real(c_double) :: zfoeeliq_loc
    real(c_double) :: zfoeeice_loc
    real(c_double) :: zfoeewm_loc
    real(c_double) :: zdelta
    integer(c_int64_t) :: t1_, t2_, rate_

    call system_clock(t1_, rate_)
    do jk = 0, (KLEV) - 1
        do jl = 0, (KLON) - 1
            ptare = ztp1((jk) + 1, (jl) + 1)
            zfoealfa_loc = (((max(rtice, min(rtwat, ptare)) - rtice) * rtwat_rtice_r) ** 2)
            zfoealfa_loc = min(1.0_c_double, zfoealfa_loc)
            zfoealfa((jk) + 1, (jl) + 1) = zfoealfa_loc
            zfoeeliq_loc = (r2es * EXP(((r3les * (ptare - rtt)) / (ptare - r4les))))
            zfoeeice_loc = (r2es * EXP(((r3ies * (ptare - rtt)) / (ptare - r4ies))))
            zfoeewm_loc = (r2es * ((zfoealfa_loc * EXP(((r3les * (ptare - rtt)) / (ptare - r4les)))) + ((1.0_c_double - zfoealfa_loc) * EXP(((r3ies * (ptare - rtt)) / (ptare - r4ies))))))
            zfoeewmt((jk) + 1, (jl) + 1) = min((zfoeewm_loc / pap((jk) + 1, (jl) + 1)), 0.5_c_double)
            zqsmix((jk) + 1, (jl) + 1) = zfoeewmt((jk) + 1, (jl) + 1)
            zqsmix((jk) + 1, (jl) + 1) = (zqsmix((jk) + 1, (jl) + 1) / (1.0_c_double - (retv * zqsmix((jk) + 1, (jl) + 1))))
            if ((ptare >= rtt)) then
                zdelta = 1.0_c_double
            else
                zdelta = 0.0_c_double
            end if
            zfoeew((jk) + 1, (jl) + 1) = (((zdelta * zfoeeliq_loc) + ((1.0_c_double - zdelta) * zfoeeice_loc)) / pap((jk) + 1, (jl) + 1))
            zfoeew((jk) + 1, (jl) + 1) = min(0.5_c_double, zfoeew((jk) + 1, (jl) + 1))
            zqsice((jk) + 1, (jl) + 1) = (zfoeew((jk) + 1, (jl) + 1) / (1.0_c_double - (retv * zfoeew((jk) + 1, (jl) + 1))))
            zfoeeliqt((jk) + 1, (jl) + 1) = min((zfoeeliq_loc / pap((jk) + 1, (jl) + 1)), 0.5_c_double)
            zqsliq((jk) + 1, (jl) + 1) = zfoeeliqt((jk) + 1, (jl) + 1)
            zqsliq((jk) + 1, (jl) + 1) = (zqsliq((jk) + 1, (jl) + 1) / (1.0_c_double - (retv * zqsliq((jk) + 1, (jl) + 1))))
        end do
    end do
    call system_clock(t2_)
    time_ns = (t2_ - t1_) * 1000000000_c_int64_t / rate_
end subroutine saturation_calculation_fp64
