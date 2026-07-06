! npbench-autogen -- generated from lu_solver_numpy.py; edit the numpy reference and regenerate, or delete this line to keep local edits as a hand override.
subroutine lu_solver_fp64(zqlhs, zqxn, KLON, NCLV, time_ns) bind(C, name="lu_solver_fp64")
    use, intrinsic :: iso_c_binding
    integer(c_int64_t), value, intent(in) :: KLON
    integer(c_int64_t), value, intent(in) :: NCLV
    real(c_double), intent(inout) :: zqlhs(NCLV, NCLV, KLON)
    real(c_double), intent(inout) :: zqxn(NCLV, KLON)
    integer(c_int64_t), intent(out) :: time_ns
    integer(c_int64_t) :: ik, jl, jm, jn

    integer(c_int64_t) :: t1_, t2_, rate_

    call system_clock(t1_, rate_)
    do jn = 0, ((NCLV - 1)) - 1
        do jm = (jn + 1), (NCLV) - 1
            do jl = 0, (KLON) - 1
                zqlhs((jn) + 1, (jm) + 1, (jl) + 1) = (zqlhs((jn) + 1, (jm) + 1, (jl) + 1) / zqlhs((jn) + 1, (jn) + 1, (jl) + 1))
            end do
            do ik = (jn + 1), (NCLV) - 1
                do jl = 0, (KLON) - 1
                    zqlhs((ik) + 1, (jm) + 1, (jl) + 1) = (zqlhs((ik) + 1, (jm) + 1, (jl) + 1) - (zqlhs((jn) + 1, (jm) + 1, (jl) + 1) * zqlhs((ik) + 1, (jn) + 1, (jl) + 1)))
                end do
            end do
        end do
    end do
    do jn = 1, (NCLV) - 1
        do jm = 0, (jn) - 1
            do jl = 0, (KLON) - 1
                zqxn((jn) + 1, (jl) + 1) = (zqxn((jn) + 1, (jl) + 1) - (zqlhs((jm) + 1, (jn) + 1, (jl) + 1) * zqxn((jm) + 1, (jl) + 1)))
            end do
        end do
    end do
    do jl = 0, (KLON) - 1
        zqxn(((NCLV - 1)) + 1, (jl) + 1) = (zqxn(((NCLV - 1)) + 1, (jl) + 1) / zqlhs(((NCLV - 1)) + 1, ((NCLV - 1)) + 1, (jl) + 1))
    end do
    do jn = (NCLV - 2), ((-(1))) + 1, (-(1))
        do jm = (jn + 1), (NCLV) - 1
            do jl = 0, (KLON) - 1
                zqxn((jn) + 1, (jl) + 1) = (zqxn((jn) + 1, (jl) + 1) - (zqlhs((jm) + 1, (jn) + 1, (jl) + 1) * zqxn((jm) + 1, (jl) + 1)))
            end do
        end do
        do jl = 0, (KLON) - 1
            zqxn((jn) + 1, (jl) + 1) = (zqxn((jn) + 1, (jl) + 1) / zqlhs((jn) + 1, (jn) + 1, (jl) + 1))
        end do
    end do
    call system_clock(t2_)
    time_ns = (t2_ - t1_) * 1000000000_c_int64_t / rate_
end subroutine lu_solver_fp64
