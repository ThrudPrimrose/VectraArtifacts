! npbench-autogen -- generated from autoconversion_snow_numpy.py; edit the numpy reference and regenerate, or delete this line to keep local edits as a hand override.
subroutine autoconversion_snow_fp64(pnice, zicecld, zsnowaut, zsolqb, ztp1, KLON, NCLDQI, NCLDQS, laericeauto, ptsphy, rlcritsnow, rnice, rsnowlin1, rsnowlin2, rtt, zepsec, time_ns) bind(C, name="autoconversion_snow_fp64")
    use, intrinsic :: iso_c_binding
    integer(c_int64_t), value, intent(in) :: KLON
    integer(c_int64_t), value, intent(in) :: NCLDQI
    integer(c_int64_t), value, intent(in) :: NCLDQS
    integer(c_int64_t), value, intent(in) :: laericeauto
    real(c_double), intent(in) :: pnice(KLON)
    real(c_double), intent(in) :: zicecld(KLON)
    real(c_double), intent(inout) :: zsnowaut(KLON)
    real(c_double), intent(inout) :: zsolqb(NCLDQI, NCLDQS, KLON)
    real(c_double), intent(in) :: ztp1(KLON)
    real(c_double), value, intent(in) :: ptsphy
    real(c_double), value, intent(in) :: rlcritsnow
    real(c_double), value, intent(in) :: rnice
    real(c_double), value, intent(in) :: rsnowlin1
    real(c_double), value, intent(in) :: rsnowlin2
    real(c_double), value, intent(in) :: rtt
    real(c_double), value, intent(in) :: zepsec
    integer(c_int64_t), intent(out) :: time_ns
    integer(c_int64_t) :: jl
    real(c_double) :: zzco
    real(c_double) :: zlcrit
    integer(c_int64_t) :: t1_, t2_, rate_

    call system_clock(t1_, rate_)
    do jl = 0, (KLON) - 1
        zsnowaut((jl) + 1) = 0.0_c_double
    end do
    do jl = 0, (KLON) - 1
        if ((ztp1((jl) + 1) <= rtt)) then
            if ((zicecld((jl) + 1) > zepsec)) then
                zzco = ((ptsphy * rsnowlin1) * EXP((rsnowlin2 * (ztp1((jl) + 1) - rtt))))
                if ((laericeauto /= 0)) then
                    zlcrit = rlcritsnow
                    zzco = (zzco * ((rnice / pnice((jl) + 1)) ** 0.333_c_double))
                else
                    zlcrit = rlcritsnow
                end if
                zsnowaut((jl) + 1) = (zzco * (1.0_c_double - EXP((-(((zicecld((jl) + 1) / zlcrit) ** 2))))))
                zsolqb(((NCLDQI - 1)) + 1, ((NCLDQS - 1)) + 1, (jl) + 1) = (zsolqb(((NCLDQI - 1)) + 1, ((NCLDQS - 1)) + 1, (jl) + 1) + zsnowaut((jl) + 1))
            end if
        end if
    end do
    call system_clock(t2_)
    time_ns = (t2_ - t1_) * 1000000000_c_int64_t / rate_
end subroutine autoconversion_snow_fp64
