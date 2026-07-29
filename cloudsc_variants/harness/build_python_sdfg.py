"""Build a DaCe SDFG from a ``@dace.program`` (the Python frontend) and save it.

    python build_python_sdfg.py <module.py> <func> <out.sdfg>

Run under py12 with the dace *main* worktree on PYTHONPATH so the SDFG is
produced by (and therefore guaranteed loadable on) main:

    PYTHONPATH=/home/primrose/Work/dace-main-wt python build_python_sdfg.py ...
"""
import importlib.util
import os
import sys
import types

# DaCe's Python frontend unconditionally runs ``MPIResolver``, which does
# ``from mpi4py import MPI``. In this environment MPI_Init hangs (the MPI
# runtime can't initialise -- UCX inotify watch limit / sandboxed network),
# so the import never returns and never raises (the resolver's try/except
# only catches ImportError). These CloudSC kernels use no MPI, so we stub
# mpi4py before importing dace; MPIResolver then finds nothing to rewrite.
if "mpi4py" not in sys.modules:
    _mpi = types.ModuleType("mpi4py.MPI")
    _mpi.Comm = type("Comm", (), {})  # MPIResolver does isinstance(obj, MPI.Comm)
    _mpi.Intracomm = type("Intracomm", (), {})
    _mpi.COMM_WORLD = None
    _mpi.COMM_NULL = None
    _m = types.ModuleType("mpi4py")
    _m.MPI = _mpi
    sys.modules["mpi4py"] = _m
    sys.modules["mpi4py.MPI"] = _mpi

import dace


def build(mod_path, func_name, out_path):
    """Trace ``mod_path::func_name`` to an SDFG, save to ``out_path``, return the SDFG."""
    spec = importlib.util.spec_from_file_location("kern", mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    prog = vars(mod)[func_name]
    sdfg = prog.to_sdfg(simplify=False)
    # Distinct name from the Fortran-frontend SDFG so the two never collide
    # in .dacecache when both are compiled in the same harness.
    sdfg.name = os.path.splitext(os.path.basename(out_path))[0]
    sdfg.save(out_path)
    print(f"[python-frontend] {mod_path}::{func_name} -> {out_path}")
    print(f"  name={sdfg.name}")
    print(f"  arrays={list(sdfg.arrays.keys())}")
    print(f"  symbols={list(sdfg.symbols.keys())}")
    return sdfg


def main() -> int:
    build(sys.argv[1], sys.argv[2], sys.argv[3])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
