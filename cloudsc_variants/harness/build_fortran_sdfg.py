"""Build a DaCe SDFG from a Fortran source via the dace-fortran (HLFIR/flang)
frontend and save it to disk.

Runs under pyenv ``py13`` with the FaCe branch of DaCe on PYTHONPATH:

    PYTHONPATH=/home/primrose/Work/d-face:/home/primrose/Work/dace-fortran \
        python build_fortran_sdfg.py <src.f90> <out.sdfg> [entry]

``entry`` is optional; when omitted the single procedure in the file is
auto-resolved (the contract dace-fortran enforces for single-proc TUs).
We feed the NON-bind(C), no-timer variant here -- the SDFG frontend wants
the plain Fortran procedure, while the bind(C)+timer variant is reserved
for the ctypes call in the numerical-correctness harness.
"""
import os
import sys

import dace_fortran


def build(src_path, out_path, entry=None):
    """Lower ``src_path`` through dace-fortran, save to ``out_path``, return the SDFG."""
    src = open(src_path).read()
    # Distinct name from the Python-frontend SDFG (the Fortran subroutine name would
    # otherwise clash with the @dace.program name) so both compile without a cache collision.
    name = os.path.splitext(os.path.basename(out_path))[0]
    sdfg = dace_fortran.build_sdfg(src, entry=entry, name=name)
    # The new (FaCe) Fortran frontend emits library nodes (e.g. Memset/Copy)
    # that the old `main`-branch codegen cannot lower. Expand them here --
    # in the py13/FaCe env where those nodes' expansions are registered --
    # so the saved SDFG is plain maps/tasklets that main can codegen too.
    sdfg.expand_library_nodes()
    sdfg.name = name
    sdfg.save(out_path)
    print(f"[fortran-frontend] {src_path} -> {out_path}")
    print(f"  name={sdfg.name}")
    print(f"  arrays={list(sdfg.arrays.keys())}")
    print(f"  symbols={list(sdfg.symbols.keys())}")
    return sdfg


def main() -> int:
    entry = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "-" else None
    build(sys.argv[1], sys.argv[2], entry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
