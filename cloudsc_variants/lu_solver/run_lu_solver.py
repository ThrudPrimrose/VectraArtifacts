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

KLON, NCLV = 4096, 5
RTOL = 1e-9


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
    spec = importlib.util.spec_from_file_location("ref", os.path.join(HERE, "lu_solver_numpy.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    a = {k: v.copy() for k, v in arrays.items()}
    mod.lu_solver_microphysics(a["zqlhs"], a["zqxn"], KLON, NCLV)
    return {"zqlhs": a["zqlhs"], "zqxn": a["zqxn"]}


def run_original_fortran(arrays):
    so = os.path.join(HERE, "liblu_solver_orig.so")
    if not os.path.exists(so):
        subprocess.run(["gfortran", "-O3", "-fPIC", "-shared", "-ffast-math", "-fno-math-errno",
                        os.path.join(HERE, "lu_solver_w_timer.f90"), "-o", so], check=True)
    lib = ctypes.CDLL(so)
    fn = lib.lu_solver_microphysics
    fn.restype = None
    nd1 = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags="F_CONTIGUOUS")
    nd2 = np.ctypeslib.ndpointer(dtype=np.float64, ndim=2, flags="F_CONTIGUOUS")
    nd3 = np.ctypeslib.ndpointer(dtype=np.float64, ndim=3, flags="F_CONTIGUOUS")
    fn.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, nd3, nd2, nd1]
    zqlhs = np.asfortranarray(arrays["zqlhs"].copy())
    zqxn = np.asfortranarray(arrays["zqxn"].copy())
    timer = np.zeros(2)
    fn(1, KLON, KLON, NCLV, zqlhs, zqxn, timer)
    return {"zqlhs": zqlhs, "zqxn": zqxn}


def run_native(arrays, lang_map, lang):
    so, binding = lang_map[lang]
    bufs = {"zqlhs": np.ascontiguousarray(arrays["zqlhs"].copy()),
            "zqxn": np.ascontiguousarray(arrays["zqxn"].copy())}
    native.call_native(so, binding, dict(KLON=KLON, NCLV=NCLV), bufs)
    return {"zqlhs": bufs["zqlhs"], "zqxn": bufs["zqxn"]}


def run_sdfg(tag, arrays, fortran_layout):
    import dace
    sdfg = dace.SDFG.from_file(os.path.join(HERE, f"lu_solver_{tag}.sdfg"))
    csdfg = sdfg.compile()
    order = "F" if fortran_layout else "C"
    zqlhs = np.array(arrays["zqlhs"], order=order, copy=True)
    zqxn = np.array(arrays["zqxn"], order=order, copy=True)
    if tag == "fortran_frontend":
        csdfg(zqlhs=zqlhs, zqxn=zqxn, klon=KLON, nclv=NCLV)
    else:
        csdfg(zqlhs=zqlhs, zqxn=zqxn, KLON=KLON, NCLV=NCLV)
    return {"zqlhs": zqlhs, "zqxn": zqxn}


def main():
    arrays = make_inputs()
    ref = numpy_reference(arrays)
    print(f"lu_solver_microphysics  KLON={KLON} NCLV={NCLV}  rtol={RTOL}")
    lang_map = native.emit_and_compile_native(HERE, "lu_solver", "lu_solver_numpy.py",
                                              "lu_solver.bench_info.json")
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
