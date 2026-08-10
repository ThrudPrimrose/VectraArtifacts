"""End-to-end numerical-correctness harness for ``autoconversion_snow``.

Runs the kernel through SIX independent realisations and checks every one
against the NumPy oracle:

  1. NumPy reference            (autoconversion_snow_numpy.py)        -- oracle
  2. Original Fortran           (autoconversion_snow_w_timer.f90, bind-C, ctypes)
  3. NumpyToX autogen C         (gen/lib..._c.so)
  4. NumpyToX autogen C++       (gen/lib..._cpp.so)
  5. NumpyToX autogen Fortran   (gen/lib..._fortran.so)
  6. Fortran-frontend SDFG      (dace-fortran / FaCe)
  7. Python-frontend SDFG       (@dace.program / FaCe)

Run under pyenv py13 with the FaCe branch:
    PYTHONPATH=/home/primrose/Work/d-face:/home/primrose/Work/dace-fortran \
        python run_autoconversion_snow.py
"""
import ctypes
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "harness"))
import native  # noqa: E402

KLON, NCLDQS, NCLDQI = 2097152, 4, 2
RTOL = 1e-9
KER = "autoconversion_snow"
CONSTS = dict(rtt=273.16,
              rlcritsnow=1e-4,
              rsnowlin1=1e-3,
              rsnowlin2=0.05,
              rnice=1e7,
              ptsphy=2.0,
              zepsec=1e-12,
              laericeauto=1)
CONST_ORDER = ["rtt", "rlcritsnow", "rsnowlin1", "rsnowlin2", "rnice", "ptsphy", "zepsec"]
OUT = ("zsnowaut", "zsolqb")


# --------------------------------------------------------------------------
# inputs
# --------------------------------------------------------------------------
def make_inputs():
    rng = np.random.default_rng(0)
    return dict(
        ztp1=np.linspace(250.0, 290.0, KLON),  # straddles RTT
        zicecld=(1e-5 + 5e-4 * rng.random(KLON)),
        pnice=(0.5e7 + 1.5e7 * rng.random(KLON)),
        zsnowaut=np.zeros(KLON),
        zsolqb=np.zeros((KLON, NCLDQS, NCLDQI)),
    )


def numpy_reference(arrays):
    import importlib.util
    spec = importlib.util.spec_from_file_location("ref", os.path.join(HERE, f"{KER}_numpy.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    a = {k: v.copy() for k, v in arrays.items()}
    mod.autoconversion_snow(a["ztp1"], a["zicecld"], a["pnice"], a["zsolqb"], a["zsnowaut"],
                            *[CONSTS[k] for k in CONST_ORDER], CONSTS["laericeauto"], KLON, NCLDQS, NCLDQI)
    return {k: a[k] for k in OUT}


# --------------------------------------------------------------------------
# original Fortran (.so via ctypes), bind-C with timer
# --------------------------------------------------------------------------
def run_original_fortran(arrays, timer_out=None):
    so = os.path.join(HERE, f"lib{KER}_orig.so")
    if not os.path.exists(so):
        subprocess.run([
            "gfortran", "-O3", "-fPIC", "-shared", "-ffast-math", "-fno-math-errno",
            os.path.join(HERE, f"{KER}_w_timer.f90"), "-o", so
        ],
                       check=True)
    lib = ctypes.CDLL(so)
    fn = lib.autoconversion_snow
    fn.restype = None
    nd1 = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags="F_CONTIGUOUS")
    nd3 = np.ctypeslib.ndpointer(dtype=np.float64, ndim=3, flags="F_CONTIGUOUS")
    fn.argtypes = [
        ctypes.c_int, ctypes.c_int, ctypes.c_int, nd1, nd1, nd1, nd3, nd1, ctypes.c_double, ctypes.c_double,
        ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_bool,
        ctypes.c_int, ctypes.c_int, nd1
    ]
    ztp1 = np.asfortranarray(arrays["ztp1"].copy())
    zicecld = np.asfortranarray(arrays["zicecld"].copy())
    pnice = np.asfortranarray(arrays["pnice"].copy())
    zsolqb = np.asfortranarray(arrays["zsolqb"].copy())
    zsnowaut = np.asfortranarray(arrays["zsnowaut"].copy())
    timer = timer_out if timer_out is not None else np.zeros(2)
    fn(1, KLON, KLON, ztp1, zicecld, pnice, zsolqb, zsnowaut, *[CONSTS[k] for k in CONST_ORDER],
       bool(CONSTS["laericeauto"]), NCLDQS, NCLDQI, timer)
    return {"zsnowaut": zsnowaut, "zsolqb": zsolqb}


# --------------------------------------------------------------------------
# NumpyToX autogen C / C++ / Fortran (one ABI, three .so)
# --------------------------------------------------------------------------
def run_native(arrays, lang_map, lang):
    so, binding = lang_map[lang]
    env = dict(CONSTS, KLON=KLON, NCLDQS=NCLDQS, NCLDQI=NCLDQI)
    bufs = {
        "ztp1": np.ascontiguousarray(arrays["ztp1"]),
        "zicecld": np.ascontiguousarray(arrays["zicecld"]),
        "pnice": np.ascontiguousarray(arrays["pnice"]),
        "zsnowaut": np.ascontiguousarray(arrays["zsnowaut"].copy()),
        "zsolqb": np.ascontiguousarray(arrays["zsolqb"].copy()),
    }
    native.call_native(so, binding, env, bufs)
    return {"zsnowaut": bufs["zsnowaut"], "zsolqb": bufs["zsolqb"]}


# --------------------------------------------------------------------------
# SDFG variants (compiled in FaCe)
# --------------------------------------------------------------------------
def sdfg_kwargs(tag, a):
    """Array + symbol kwargs for one compiled-SDFG call; ``a`` holds the live buffers."""
    sc = {k: np.float64(CONSTS[k]) for k in CONST_ORDER}
    if tag == "fortran_frontend":
        # The Fortran frontend types LAERICEAUTO as LOGICAL and carries KFDIA as its own symbol.
        return dict(**a,
                    **sc,
                    laericeauto=np.bool_(CONSTS["laericeauto"] != 0),
                    kfdia=KLON,
                    klon=KLON,
                    ncldqi=NCLDQI,
                    ncldqs=NCLDQS)
    return dict(**a, **sc, laericeauto=np.int64(CONSTS["laericeauto"]), KLON=KLON, NCLDQI=NCLDQI, NCLDQS=NCLDQS)


def run_sdfg(tag, arrays, fortran_layout):
    import dace
    sdfg = dace.SDFG.from_file(os.path.join(HERE, f"{KER}_{tag}.sdfg"))
    csdfg = sdfg.compile()
    # DaCe rejects array *views*; every buffer must be a fresh owning copy.
    order = "F" if fortran_layout else "C"
    a = {k: np.array(v, order=order, copy=True) for k, v in arrays.items()}
    csdfg(**sdfg_kwargs(tag, a))
    return {k: a[k] for k in OUT}


def main():
    arrays = make_inputs()
    ref = numpy_reference(arrays)
    print(f"{KER}  KLON={KLON} NCLDQS={NCLDQS} NCLDQI={NCLDQI}  rtol={RTOL}")
    print(f"  oracle: nonzero zsnowaut = {int(np.count_nonzero(ref['zsnowaut']))}/{KLON}")

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
