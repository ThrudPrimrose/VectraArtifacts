"""Regenerate every CloudSC-variant SDFG artifact from its source.

Five variants x two frontends = ten ``.sdfg`` files:

    <variant>/<variant>_fortran_frontend.sdfg   from <variant>_no_bind.f90 via dace-fortran
    <variant>/<variant>_python_frontend.sdfg    from <variant>_dace.py     via @dace.program

Idempotent: re-running reproduces the same files, and it works from a clean tree
with all ten absent. Reach for this whenever d-face or dace-fortran changes and
the checked-in artifacts stop loading -- a saved SDFG is only valid for the
serialization format of the DaCe that wrote it.

Run under pyenv py13 with the FaCe branch on PYTHONPATH (see run_all.sh):

    PYTHONPATH=/home/primrose/Work/d-face:/home/primrose/Work/dace-fortran \
        python regen_sdfgs.py [--only <variant>] [--frontend fortran|python|both]
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "harness"))

# Import order matters: build_python_sdfg installs an mpi4py stub at import time and
# that only takes effect while mpi4py is still unimported, so it must precede the
# dace-fortran import (which pulls in dace, and with it the real mpi4py).
import build_python_sdfg  # noqa: E402
import build_fortran_sdfg  # noqa: E402

VARIANTS = ("autoconversion_snow", "ice_supersaturation_adjustment", "lu_solver", "rain_evaporation_abel_boutle",
            "saturation_calculation")


def entry_name(variant):
    """The kernel's procedure name, as declared in the variant's bench_info manifest."""
    manifest = os.path.join(HERE, variant, f"{variant}.bench_info.json")
    return json.load(open(manifest))["func_name"]


def sdfg_path(variant, frontend):
    return os.path.join(HERE, variant, f"{variant}_{frontend}_frontend.sdfg")


def regen(variant, frontend):
    """Regenerate one artifact and return its path."""
    out = sdfg_path(variant, frontend)
    if frontend == "fortran":
        # The BIND(C)-stripped, timer-free source is what the SDFG frontend accepts;
        # the bind-C _w_timer variant is reserved for the ctypes reference lane.
        build_fortran_sdfg.build(os.path.join(HERE, variant, f"{variant}_no_bind.f90"), out)
    else:
        build_python_sdfg.build(os.path.join(HERE, variant, f"{variant}_dace.py"), entry_name(variant), out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", choices=VARIANTS, help="regenerate a single variant (default: all)")
    ap.add_argument("--frontend", choices=("fortran", "python", "both"), default="both")
    args = ap.parse_args()

    variants = (args.only, ) if args.only else VARIANTS
    frontends = ("fortran", "python") if args.frontend == "both" else (args.frontend, )

    written = []
    for variant in variants:
        for frontend in frontends:
            written.append(regen(variant, frontend))
    print(f"\nregenerated {len(written)} SDFG(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
