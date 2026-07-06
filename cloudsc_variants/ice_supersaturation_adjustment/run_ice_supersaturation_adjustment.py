"""End-to-end numerical-correctness harness for ``ice_supersaturation_adjustment``.

Six realisations vs the NumPy oracle. Run under py13 / FaCe:
    PYTHONPATH=/home/primrose/Work/d-face:/home/primrose/Work/dace-fortran \
        python run_ice_supersaturation_adjustment.py
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
NCLDQL, NCLDQI, NCLDQV = 1, 2, 5
RTOL = 1e-9
CONSTS = dict(rtt=273.16, ramin=1e-6, rthomo=235.16, rkooptau=1e4,
              ptsphy=2.0, zepsec=1e-12, nssopt=1)
KER = "ice_supersaturation_adjustment"


def make_inputs():
    rng = np.random.default_rng(0)
    return dict(
        ztp1=np.linspace(230.0, 290.0, KLON),                 # straddles RTHOMO & RTT
        za=(0.4 + 0.6 * rng.random(KLON)),                    # some > 1-RAMIN
        zqx_ncldqv=(1e-3 + 1e-3 * rng.random(KLON)),
        zqsice=(5e-4 + 1e-3 * rng.random(KLON)),
        zcorqsice=(0.5 + rng.random(KLON)),                   # nonzero divisor
        zfokoop=(0.5 + 1.5 * rng.random(KLON)),
        zsolqa=np.zeros((KLON, NCLV, NCLV)),
        zsolac=np.zeros(KLON),
        zqxfg=np.zeros((KLON, NCLV)),
    )


def numpy_reference(arrays):
    import importlib.util
    spec = importlib.util.spec_from_file_location("ref", os.path.join(HERE, f"{KER}_numpy.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    a = {k: v.copy() for k, v in arrays.items()}
    mod.ice_supersaturation_adjustment(
        a["ztp1"], a["za"], a["zqx_ncldqv"], a["zqsice"], a["zcorqsice"], a["zfokoop"],
        a["zsolqa"], a["zsolac"], a["zqxfg"],
        CONSTS["rtt"], CONSTS["ramin"], CONSTS["rthomo"], CONSTS["rkooptau"],
        CONSTS["ptsphy"], CONSTS["zepsec"], CONSTS["nssopt"],
        KLON, NCLV, NCLDQL, NCLDQI, NCLDQV)
    return {k: a[k] for k in ("zsolqa", "zsolac", "zqxfg")}


def run_original_fortran(arrays):
    so = os.path.join(HERE, f"lib{KER}_orig.so")
    if not os.path.exists(so):
        subprocess.run(["gfortran", "-O3", "-fPIC", "-shared", "-ffast-math", "-fno-math-errno",
                        os.path.join(HERE, f"{KER}_w_timer.f90"), "-o", so], check=True)
    lib = ctypes.CDLL(so)
    fn = lib.ice_supersaturation_adjustment
    fn.restype = None
    nd1 = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags="F_CONTIGUOUS")
    nd2 = np.ctypeslib.ndpointer(dtype=np.float64, ndim=2, flags="F_CONTIGUOUS")
    nd3 = np.ctypeslib.ndpointer(dtype=np.float64, ndim=3, flags="F_CONTIGUOUS")
    ci, cd = ctypes.c_int, ctypes.c_double
    fn.argtypes = [ci, ci, ci, nd1, nd1, nd1, nd1, nd1, nd1, nd3, nd1, nd2,
                   cd, cd, cd, ci, cd, cd, cd, ci, ci, ci, ci, nd1]
    a = {k: (np.asfortranarray(v.copy()) if v.ndim >= 2 else np.asfortranarray(v.copy()))
         for k, v in arrays.items()}
    timer = np.zeros(2)
    fn(1, KLON, KLON, a["ztp1"], a["za"], a["zqx_ncldqv"], a["zqsice"], a["zcorqsice"],
       a["zfokoop"], a["zsolqa"], a["zsolac"], a["zqxfg"],
       CONSTS["rtt"], CONSTS["ramin"], CONSTS["rthomo"], int(CONSTS["nssopt"]),
       CONSTS["rkooptau"], CONSTS["ptsphy"], CONSTS["zepsec"],
       NCLDQL, NCLDQI, NCLDQV, NCLV, timer)
    return {k: a[k] for k in ("zsolqa", "zsolac", "zqxfg")}


def run_native(arrays, lang_map, lang):
    so, binding = lang_map[lang]
    env = dict(CONSTS, KLON=KLON, NCLV=NCLV, NCLDQL=NCLDQL, NCLDQI=NCLDQI, NCLDQV=NCLDQV)
    bufs = {k: np.ascontiguousarray(v.copy()) for k, v in arrays.items()}
    native.call_native(so, binding, env, bufs)
    return {k: bufs[k] for k in ("zsolqa", "zsolac", "zqxfg")}


def run_sdfg(tag, arrays, fortran_layout):
    import dace
    sdfg = dace.SDFG.from_file(os.path.join(HERE, f"{KER}_{tag}.sdfg"))
    csdfg = sdfg.compile()
    order = "F" if fortran_layout else "C"
    a = {k: np.array(v, order=order, copy=True) for k, v in arrays.items()}
    sc = {k: np.float64(CONSTS[k]) for k in ("rtt", "ramin", "rthomo", "rkooptau", "ptsphy", "zepsec")}
    if tag == "fortran_frontend":
        csdfg(**a, **sc, nssopt=np.int64(CONSTS["nssopt"]),
              klon=KLON, nclv=NCLV, ncldql=NCLDQL, ncldqi=NCLDQI, ncldqv=NCLDQV)
    else:
        csdfg(**a, **sc, nssopt=np.int64(CONSTS["nssopt"]),
              KLON=KLON, NCLV=NCLV, NCLDQL=NCLDQL, NCLDQI=NCLDQI, NCLDQV=NCLDQV)
    return {k: a[k] for k in ("zsolqa", "zsolac", "zqxfg")}


def main():
    arrays = make_inputs()
    ref = numpy_reference(arrays)
    print(f"{KER}  KLON={KLON} NCLV={NCLV}  rtol={RTOL}")
    print(f"  oracle: nonzero zsolac = {int(np.count_nonzero(ref['zsolac']))}/{KLON}")
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
