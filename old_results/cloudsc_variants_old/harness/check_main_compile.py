"""Attempt to load + compile a saved SDFG on the DaCe ``main`` branch.

    PYTHONPATH=/home/primrose/Work/dace-main-wt python check_main_compile.py <a.sdfg> [<b.sdfg> ...]

Prints LOAD/COMPILE OK or the failure reason for each. Used to document
whether the FaCe-frontend and Python-frontend SDFGs are portable to
main's (older) deserializer + codegen.
"""
import sys
import types

# Same mpi4py stub as build_python_sdfg.py -- compiling a Python-frontend
# SDFG re-enters frontend code paths that import mpi4py.
if "mpi4py" not in sys.modules:
    _mpi = types.ModuleType("mpi4py.MPI")
    _mpi.Comm = type("Comm", (), {})
    _mpi.Intracomm = type("Intracomm", (), {})
    _mpi.COMM_WORLD = None
    _m = types.ModuleType("mpi4py")
    _m.MPI = _mpi
    sys.modules["mpi4py"] = _m
    sys.modules["mpi4py.MPI"] = _mpi

import dace  # noqa: E402


def main() -> int:
    print(f"dace from: {dace.__path__}")
    rc = 0
    for path in sys.argv[1:]:
        name = path.split("/")[-1]
        try:
            sdfg = dace.SDFG.from_file(path)
        except Exception as e:
            print(f"  [LOAD FAIL]    {name}: {type(e).__name__}: {str(e)[:140]}")
            rc = 1
            continue
        try:
            sdfg.compile()
            print(f"  [COMPILE OK]   {name}")
        except Exception as e:
            print(f"  [COMPILE FAIL] {name}: {type(e).__name__}: {str(e)[:140]}")
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
