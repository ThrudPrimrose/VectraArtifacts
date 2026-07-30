"""End-to-end numerical-correctness harness for ``rain_evaporation_abel_boutle``.

Six realisations vs the NumPy oracle. Run under py13 / FaCe:
    PYTHONPATH=/home/primrose/Work/d-face:/home/primrose/Work/dace-fortran \
        python run_rain_evaporation_abel_boutle.py
"""
import ctypes
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "harness"))
import native  # noqa: E402

KLON, NCLV = 4194304, 5
NCLDQV, NCLDQR = 5, 3
RTOL = 1e-9
KER = "rain_evaporation_abel_boutle"

# scalar constants (order independent -- referenced by name)
CONSTS = dict(rtt=273.16, rv=461.5, rd=287.0, rprecrhmax=0.7, rcovpmin=0.1,
              rdensref=1.0, ptsphy=2.0, zepsec=1e-12,
              rcl_fac1=5.0, rcl_fac2=0.5, rcl_cdenom1=1.0, rcl_cdenom2=1e-3,
              rcl_cdenom3=1e-6, rcl_ka273=0.024, rcl_const1r=1.0, rcl_const2r=0.31,
              rcl_const3r=0.5, rcl_const4r=0.5)
# original-Fortran positional order of the scalar block
CONST_ORDER = ["rtt", "rv", "rd", "rprecrhmax", "rcovpmin", "rdensref", "ptsphy", "zepsec",
               "rcl_fac1", "rcl_fac2", "rcl_cdenom1", "rcl_cdenom2", "rcl_cdenom3",
               "rcl_ka273", "rcl_const1r", "rcl_const2r", "rcl_const3r", "rcl_const4r"]
OUT = ("zqxfg_ncldqr", "zcovptot", "zsolqa", "zevap_out")


def make_inputs():
    rng = np.random.default_rng(0)
    return dict(
        ztp1=np.linspace(270.0, 290.0, KLON),
        zqx_ncldqv=(8e-4 + 8e-4 * rng.random(KLON)),
        za=(0.6 * rng.random(KLON)),
        zqsliq=(1.5e-3 + 1.5e-3 * rng.random(KLON)),
        zqxfg_ncldqr=(1e-4 + 9e-4 * rng.random(KLON)),
        zcovptot=(0.3 + 0.7 * rng.random(KLON)),
        zcovpclr=(0.2 + 0.7 * rng.random(KLON)),
        zcovpmax=(0.2 + 0.8 * rng.random(KLON)),
        zrho=(0.8 + 0.4 * rng.random(KLON)),
        pap=(5e4 + 5e4 * rng.random(KLON)),
        zsolqa=np.zeros((KLON, NCLV, NCLV)),
        zevap_out=np.zeros(KLON),
    )


def numpy_reference(arrays):
    import importlib.util
    spec = importlib.util.spec_from_file_location("ref", os.path.join(HERE, f"{KER}_numpy.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    a = {k: v.copy() for k, v in arrays.items()}
    mod.rain_evaporation_abel_boutle(
        a["ztp1"], a["zqx_ncldqv"], a["za"], a["zqsliq"], a["zqxfg_ncldqr"], a["zcovptot"],
        a["zcovpclr"], a["zcovpmax"], a["zrho"], a["pap"], a["zsolqa"], a["zevap_out"],
        *[CONSTS[k] for k in CONST_ORDER], KLON, NCLV, NCLDQV, NCLDQR)
    return {k: a[k] for k in OUT}


def run_original_fortran(arrays):
    so = os.path.join(HERE, f"lib{KER}_orig.so")
    if not os.path.exists(so):
        subprocess.run(["gfortran", "-O3", "-fPIC", "-shared", "-ffast-math", "-fno-math-errno",
                        os.path.join(HERE, f"{KER}_w_timer.f90"), "-o", so], check=True)
    lib = ctypes.CDLL(so)
    fn = lib.rain_evaporation_abel_boutle
    fn.restype = None
    nd1 = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags="F_CONTIGUOUS")
    nd3 = np.ctypeslib.ndpointer(dtype=np.float64, ndim=3, flags="F_CONTIGUOUS")
    ci, cd = ctypes.c_int, ctypes.c_double
    fn.argtypes = ([ci, ci, ci] + [nd1] * 5 + [nd1] * 4 + [nd1] + [nd3, nd1]
                   + [cd] * 18 + [ci, ci, ci, nd1])
    a = {k: np.asfortranarray(v.copy()) for k, v in arrays.items()}
    timer = np.zeros(2)
    fn(1, KLON, KLON,
       a["ztp1"], a["zqx_ncldqv"], a["za"], a["zqsliq"], a["zqxfg_ncldqr"],
       a["zcovptot"], a["zcovpclr"], a["zcovpmax"], a["zrho"], a["pap"],
       a["zsolqa"], a["zevap_out"],
       *[CONSTS[k] for k in CONST_ORDER],
       NCLDQV, NCLDQR, NCLV, timer)
    return {k: a[k] for k in OUT}


def run_native(arrays, lang_map, lang):
    so, binding = lang_map[lang]
    env = dict(CONSTS, KLON=KLON, NCLV=NCLV, NCLDQV=NCLDQV, NCLDQR=NCLDQR)
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
        csdfg(**a, **sc, klon=KLON, nclv=NCLV, ncldqv=NCLDQV, ncldqr=NCLDQR)
    else:
        csdfg(**a, **sc, KLON=KLON, NCLV=NCLV, NCLDQV=NCLDQV, NCLDQR=NCLDQR)
    return {k: a[k] for k in OUT}


def main():
    arrays = make_inputs()
    ref = numpy_reference(arrays)
    print(f"{KER}  KLON={KLON} NCLV={NCLV}  rtol={RTOL}")
    print(f"  oracle: nonzero zevap_out = {int(np.count_nonzero(ref['zevap_out']))}/{KLON}")
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
