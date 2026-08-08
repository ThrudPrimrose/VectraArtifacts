"""DaCe Python-frontend version of ``lu_solver_microphysics``."""
import dace

KLON = dace.symbol("KLON")
NCLV = dace.symbol("NCLV")


@dace.program
def lu_solver_microphysics(zqlhs: dace.float64[KLON, NCLV, NCLV],
                           zqxn: dace.float64[KLON, NCLV]):
    for jn in range(0, NCLV - 1):
        for jm in range(jn + 1, NCLV):
            for jl in range(0, KLON):
                zqlhs[jl, jm, jn] = zqlhs[jl, jm, jn] / zqlhs[jl, jn, jn]
            for ik in range(jn + 1, NCLV):
                for jl in range(0, KLON):
                    zqlhs[jl, jm, ik] = zqlhs[jl, jm, ik] - (zqlhs[jl, jm, jn] * zqlhs[jl, jn, ik])

    for jn in range(1, NCLV):
        for jm in range(0, jn):
            for jl in range(0, KLON):
                zqxn[jl, jn] = zqxn[jl, jn] - (zqlhs[jl, jn, jm] * zqxn[jl, jm])

    for jl in range(0, KLON):
        zqxn[jl, NCLV - 1] = zqxn[jl, NCLV - 1] / zqlhs[jl, NCLV - 1, NCLV - 1]

    for jn in range(NCLV - 2, -1, -1):
        for jm in range(jn + 1, NCLV):
            for jl in range(0, KLON):
                zqxn[jl, jn] = zqxn[jl, jn] - (zqlhs[jl, jn, jm] * zqxn[jl, jm])
        for jl in range(0, KLON):
            zqxn[jl, jn] = zqxn[jl, jn] / zqlhs[jl, jn, jn]
