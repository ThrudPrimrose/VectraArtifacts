"""Manual NumPy port of the CloudSC ``lu_solver_microphysics`` loop nest.

Per-column (JL) LU factorisation without pivoting + forward/backward
substitution, transcribed 1:1 from ``cloudsc_loopnests/lu_solver.f90``
(Fortran 1-based -> 0-based). ``zqlhs`` (factored in place) and ``zqxn``
(the solution) are both mutated outputs.
"""


def lu_solver_microphysics(zqlhs, zqxn, KLON, NCLV):
    # LU factorisation (per column jl)
    for jn in range(0, NCLV - 1):
        for jm in range(jn + 1, NCLV):
            for jl in range(0, KLON):
                zqlhs[jl, jm, jn] = zqlhs[jl, jm, jn] / zqlhs[jl, jn, jn]
            for ik in range(jn + 1, NCLV):
                for jl in range(0, KLON):
                    zqlhs[jl, jm, ik] = zqlhs[jl, jm, ik] - (zqlhs[jl, jm, jn] * zqlhs[jl, jn, ik])

    # Forward substitution
    for jn in range(1, NCLV):
        for jm in range(0, jn):
            for jl in range(0, KLON):
                zqxn[jl, jn] = zqxn[jl, jn] - (zqlhs[jl, jn, jm] * zqxn[jl, jm])

    # Backward substitution: last variable
    for jl in range(0, KLON):
        zqxn[jl, NCLV - 1] = zqxn[jl, NCLV - 1] / zqlhs[jl, NCLV - 1, NCLV - 1]

    # Backward substitution: remaining variables
    for jn in range(NCLV - 2, -1, -1):
        for jm in range(jn + 1, NCLV):
            for jl in range(0, KLON):
                zqxn[jl, jn] = zqxn[jl, jn] - (zqlhs[jl, jn, jm] * zqxn[jl, jm])
        for jl in range(0, KLON):
            zqxn[jl, jn] = zqxn[jl, jn] / zqlhs[jl, jn, jn]
