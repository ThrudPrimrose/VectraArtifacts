! npbench-autogen -- generated from ice_supersaturation_adjustment_numpy.py; edit the numpy reference and regenerate, or delete this line to keep local edits as a hand override.
subroutine ice_supersaturation_adjustment_fp64(za, zcorqsice, zfokoop, zqsice, zqx_ncldqv, zqxfg, zsolac, zsolqa, ztp1, KLON, NCLDQI, NCLDQL, NCLDQV, NCLV, nssopt, ptsphy, ramin, rkooptau, rthomo, rtt, zepsec, time_ns) bind(C, name="ice_supersaturation_adjustment_fp64")
    use, intrinsic :: iso_c_binding
    integer(c_int64_t), value, intent(in) :: KLON
    integer(c_int64_t), value, intent(in) :: NCLDQI
    integer(c_int64_t), value, intent(in) :: NCLDQL
    integer(c_int64_t), value, intent(in) :: NCLDQV
    integer(c_int64_t), value, intent(in) :: NCLV
    integer(c_int64_t), value, intent(in) :: nssopt
    real(c_double), intent(in) :: za(KLON)
    real(c_double), intent(in) :: zcorqsice(KLON)
    real(c_double), intent(in) :: zfokoop(KLON)
    real(c_double), intent(in) :: zqsice(KLON)
    real(c_double), intent(in) :: zqx_ncldqv(KLON)
    real(c_double), intent(inout) :: zqxfg(NCLV, KLON)
    real(c_double), intent(inout) :: zsolac(KLON)
    real(c_double), intent(inout) :: zsolqa(NCLV, NCLV, KLON)
    real(c_double), intent(in) :: ztp1(KLON)
    real(c_double), value, intent(in) :: ptsphy
    real(c_double), value, intent(in) :: ramin
    real(c_double), value, intent(in) :: rkooptau
    real(c_double), value, intent(in) :: rthomo
    real(c_double), value, intent(in) :: rtt
    real(c_double), value, intent(in) :: zepsec
    integer(c_int64_t), intent(out) :: time_ns
    integer(c_int64_t) :: jl
    real(c_double) :: zepsilon
    real(c_double) :: zfac
    real(c_double) :: zfaci
    real(c_double) :: zsupsat
    real(c_double) :: zqp1env
    integer(c_int64_t) :: t1_, t2_, rate_

    call system_clock(t1_, rate_)
    zepsilon = 1e-14_c_double
    do jl = 0, (KLON) - 1
        if (((ztp1((jl) + 1) >= rtt) .OR. (nssopt == 0))) then
            zfac = 1.0_c_double
            zfaci = 1.0_c_double
        else
            zfac = (za((jl) + 1) + (zfokoop((jl) + 1) * (1.0_c_double - za((jl) + 1))))
            zfaci = (ptsphy / rkooptau)
        end if
        if ((za((jl) + 1) > (1.0_c_double - ramin))) then
            zsupsat = max(((zqx_ncldqv((jl) + 1) - (zfac * zqsice((jl) + 1))) / zcorqsice((jl) + 1)), 0.0_c_double)
        else
            zqp1env = ((zqx_ncldqv((jl) + 1) - (za((jl) + 1) * zqsice((jl) + 1))) / max((1.0_c_double - za((jl) + 1)), zepsilon))
            zsupsat = max((((1.0_c_double - za((jl) + 1)) * (zqp1env - (zfac * zqsice((jl) + 1)))) / zcorqsice((jl) + 1)), 0.0_c_double)
        end if
        if ((zsupsat > zepsec)) then
            if ((ztp1((jl) + 1) > rthomo)) then
                zsolqa(((NCLDQV - 1)) + 1, ((NCLDQL - 1)) + 1, (jl) + 1) = (zsolqa(((NCLDQV - 1)) + 1, ((NCLDQL - 1)) + 1, (jl) + 1) + zsupsat)
                zsolqa(((NCLDQL - 1)) + 1, ((NCLDQV - 1)) + 1, (jl) + 1) = (zsolqa(((NCLDQL - 1)) + 1, ((NCLDQV - 1)) + 1, (jl) + 1) - zsupsat)
                zqxfg(((NCLDQL - 1)) + 1, (jl) + 1) = (zqxfg(((NCLDQL - 1)) + 1, (jl) + 1) + zsupsat)
            else
                zsolqa(((NCLDQV - 1)) + 1, ((NCLDQI - 1)) + 1, (jl) + 1) = (zsolqa(((NCLDQV - 1)) + 1, ((NCLDQI - 1)) + 1, (jl) + 1) + zsupsat)
                zsolqa(((NCLDQI - 1)) + 1, ((NCLDQV - 1)) + 1, (jl) + 1) = (zsolqa(((NCLDQI - 1)) + 1, ((NCLDQV - 1)) + 1, (jl) + 1) - zsupsat)
                zqxfg(((NCLDQI - 1)) + 1, (jl) + 1) = (zqxfg(((NCLDQI - 1)) + 1, (jl) + 1) + zsupsat)
            end if
            zsolac((jl) + 1) = ((1.0_c_double - za((jl) + 1)) * zfaci)
        end if
    end do
    call system_clock(t2_)
    time_ns = (t2_ - t1_) * 1000000000_c_int64_t / rate_
end subroutine ice_supersaturation_adjustment_fp64
