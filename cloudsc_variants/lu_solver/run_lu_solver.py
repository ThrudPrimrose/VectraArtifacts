"""End-to-end numerical-correctness harness for ``lu_solver_microphysics``.

Six realisations vs the NumPy oracle: original Fortran (bind-C ctypes),
NumpyToX autogen C / C++ / Fortran, Fortran-frontend SDFG, Python-frontend
SDFG. Run under py13 / FaCe:
    PYTHONPATH=/home/primrose/Work/d-face:/home/primrose/Work/dace-fortran \
        python run_lu_solver.py
"""
import ctypes
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "harness"))
import native  # noqa: E402

KLON, NCLV = 8388608, 5
RTOL = 1e-9
KER = "lu_solver"
CONSTS = {}  # this kernel takes no scalar physical constants
OUT = ("zqlhs", "zqxn")


def make_inputs():
    rng = np.random.default_rng(0)
    # Diagonally dominant per-column matrices: well-conditioned, no pivoting.
    zqlhs = rng.standard_normal((KLON, NCLV, NCLV))
    for d in range(NCLV):
        zqlhs[:, d, d] += NCLV + 2.0
    zqxn = rng.standard_normal((KLON, NCLV))
    return {"zqlhs": zqlhs, "zqxn": zqxn}


def numpy_reference(arrays):
    import importlib.util
    spec = importlib.util.spec_from_file_location("ref", os.path.join(HERE, f"{KER}_numpy.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    a = {k: v.copy() for k, v in arrays.items()}
    mod.lu_solver_microphysics(a["zqlhs"], a["zqxn"], KLON, NCLV)
    return {k: a[k] for k in OUT}


def run_original_fortran(arrays, timer_out=None):
    so = os.path.join(HERE, f"lib{KER}_orig.so")
    if not os.path.exists(so):
        subprocess.run([
            "gfortran", "-O3", "-fPIC", "-shared", "-ffast-math", "-fno-math-errno",
            os.path.join(HERE, f"{KER}_w_timer.f90"), "-o", so
        ],
                       check=True)
    lib = ctypes.CDLL(so)
    fn = lib.lu_solver_microphysics
    fn.restype = None
    nd1 = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags="F_CONTIGUOUS")
    nd2 = np.ctypeslib.ndpointer(dtype=np.float64, ndim=2, flags="F_CONTIGUOUS")
    nd3 = np.ctypeslib.ndpointer(dtype=np.float64, ndim=3, flags="F_CONTIGUOUS")
    fn.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, nd3, nd2, nd1]
    zqlhs = np.asfortranarray(arrays["zqlhs"].copy())
    zqxn = np.asfortranarray(arrays["zqxn"].copy())
    timer = timer_out if timer_out is not None else np.zeros(2)
    fn(1, KLON, KLON, NCLV, zqlhs, zqxn, timer)
    return {"zqlhs": zqlhs, "zqxn": zqxn}


def run_native(arrays, lang_map, lang):
    so, binding = lang_map[lang]
    bufs = {k: np.ascontiguousarray(v.copy()) for k, v in arrays.items()}
    native.call_native(so, binding, dict(CONSTS, KLON=KLON, NCLV=NCLV), bufs)
    return {k: bufs[k] for k in OUT}


def sdfg_kwargs(tag, a):
    """Array + symbol kwargs for one compiled-SDFG call; ``a`` holds the live buffers."""
    if tag == "fortran_frontend":
        return dict(**a, klon=KLON, nclv=NCLV)
    return dict(**a, KLON=KLON, NCLV=NCLV)


def run_sdfg(tag, arrays, fortran_layout):
    import dace
    sdfg = dace.SDFG.from_file(os.path.join(HERE, f"{KER}_{tag}.sdfg"))
    csdfg = sdfg.compile()
    order = "F" if fortran_layout else "C"
    a = {k: np.array(v, order=order, copy=True) for k, v in arrays.items()}
    csdfg(**sdfg_kwargs(tag, a))
    return {k: a[k] for k in OUT}


def main():
    arrays = make_inputs()
    ref = numpy_reference(arrays)
    print(f"lu_solver_microphysics  KLON={KLON} NCLV={NCLV}  rtol={RTOL}")
    lang_map = native.emit_and_compile_native(HERE, KER, f"{KER}_numpy.py", f"{KER}.bench_info.json")
    results = []
    results.append(native.compare("original Fortran (ctypes)", ref, run_original_fortran(arrays), RTOL))
    for lang in ("c", "cpp", "fortran"):
        results.append(native.compare(f"NumpyToX autogen {lang}", ref, run_native(arrays, lang_map, lang), RTOL))
    results.append(native.compare("Fortran-frontend SDFG", ref, run_sdfg("fortran_frontend", arrays, True), RTOL))
    results.append(native.compare("Python-frontend SDFG", ref, run_sdfg("python_frontend", arrays, False), RTOL))
    print()
    allok = True
    for ok, msg in results:
        print("  " + msg)
        allok = allok and ok
    print("\n" + ("ALL VARIANTS MATCH NUMPY ORACLE ✅" if allok else "SOME VARIANTS DIVERGED ❌"))
    return 0 if allok else 1


if __name__ == "__main__":
    raise SystemExit(main())
