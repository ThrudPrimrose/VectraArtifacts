"""End-to-end numerical-correctness harness for ``compute_saturation_values``.

Six realisations vs the NumPy oracle (2-D KLON x KLEV kernel). Run under
py13 / FaCe:
    PYTHONPATH=/home/primrose/Work/d-face:/home/primrose/Work/dace-fortran \
        python run_saturation_calculation.py
"""
import ctypes
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "harness"))
import native  # noqa: E402

KLON, KLEV = 4194304, 32
RTOL = 1e-9
KER = "saturation_calculation"
CONSTS = dict(rtt=273.16, retv=0.608, r2es=611.21, r3les=17.502, r3ies=22.587,
              r4les=32.19, r4ies=-0.7, rtice=250.16, rtwat=273.16, rtwat_rtice_r=0.0434782609)
CONST_ORDER = ["rtt", "retv", "r2es", "r3les", "r3ies", "r4les", "r4ies", "rtice", "rtwat", "rtwat_rtice_r"]
OUT = ("zfoealfa", "zfoeewmt", "zqsmix", "zfoeew", "zqsice", "zfoeeliqt", "zqsliq")


def make_inputs():
    rng = np.random.default_rng(0)
    z = np.zeros((KLON, KLEV))
    return dict(
        ztp1=(230.0 + 70.0 * rng.random((KLON, KLEV))),    # straddles RTICE/RTT
        pap=(5e4 + 5e4 * rng.random((KLON, KLEV))),
        zfoealfa=z.copy(), zfoeewmt=z.copy(), zqsmix=z.copy(), zfoeew=z.copy(),
        zqsice=z.copy(), zfoeeliqt=z.copy(), zqsliq=z.copy(),
    )


def numpy_reference(arrays):
    import importlib.util
    spec = importlib.util.spec_from_file_location("ref", os.path.join(HERE, f"{KER}_numpy.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    a = {k: v.copy() for k, v in arrays.items()}
    mod.compute_saturation_values(
        a["ztp1"], a["pap"], a["zfoealfa"], a["zfoeewmt"], a["zqsmix"], a["zfoeew"],
        a["zqsice"], a["zfoeeliqt"], a["zqsliq"],
        *[CONSTS[k] for k in CONST_ORDER], KLON, KLEV)
    return {k: a[k] for k in OUT}


def run_original_fortran(arrays):
    so = os.path.join(HERE, f"lib{KER}_orig.so")
    if not os.path.exists(so):
        subprocess.run(["gfortran", "-O3", "-fPIC", "-shared", "-ffast-math", "-fno-math-errno",
                        os.path.join(HERE, f"{KER}_w_timer.f90"), "-o", so], check=True)
    lib = ctypes.CDLL(so)
    fn = lib.compute_saturation_values
    fn.restype = None
    nd1 = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags="F_CONTIGUOUS")
    nd2 = np.ctypeslib.ndpointer(dtype=np.float64, ndim=2, flags="F_CONTIGUOUS")
    ci, cd = ctypes.c_int, ctypes.c_double
    fn.argtypes = [ci, ci, ci, ci] + [nd2] * 9 + [cd] * 10 + [nd1]
    a = {k: np.asfortranarray(v.copy()) for k, v in arrays.items()}
    timer = np.zeros(2)
    fn(1, KLON, KLON, KLEV,
       a["ztp1"], a["pap"], a["zfoealfa"], a["zfoeewmt"], a["zqsmix"], a["zfoeew"],
       a["zqsice"], a["zfoeeliqt"], a["zqsliq"],
       *[CONSTS[k] for k in CONST_ORDER], timer)
    return {k: a[k] for k in OUT}


def run_native(arrays, lang_map, lang):
    so, binding = lang_map[lang]
    env = dict(CONSTS, KLON=KLON, KLEV=KLEV)
    bufs = {k: np.ascontiguousarray(v.copy()) for k, v in arrays.items()}
    native.call_native(so, binding, env, bufs)
    return {k: bufs[k] for k in OUT}


def run_sdfg(tag, arrays, fortran_layout):
    import dace
    sdfg = dace.SDFG.from_file(os.path.join(HERE, f"{KER}_{tag}.sdfg"))
    csdfg = sdfg.compile()
    order = "F" if fortran_layout else "C"
    a = {k: np.array(v, order=order, copy=True) for k, v in arrays.items()}
    sc = {k: np.float64(CONSTS[k]) for k in CONST_ORDER}
    if tag == "fortran_frontend":
        csdfg(**a, **sc, klon=KLON, klev=KLEV)
    else:
        csdfg(**a, **sc, KLON=KLON, KLEV=KLEV)
    return {k: a[k] for k in OUT}


def main():
    arrays = make_inputs()
    ref = numpy_reference(arrays)
    print(f"{KER}  KLON={KLON} KLEV={KLEV}  rtol={RTOL}")
    # lang_map = native.emit_and_compile_native(HERE, KER, f"{KER}_numpy.py", f"{KER}.bench_info.json")
    results = []
    results.append(native.compare("original Fortran (ctypes)", ref, run_original_fortran(arrays), RTOL))
    # for lang in ("c", "cpp", "fortran"):
    #     results.append(native.compare(f"NumpyToX autogen {lang}", ref, run_native(arrays, lang_map, lang), RTOL))
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
