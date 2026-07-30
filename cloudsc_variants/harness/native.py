"""Shared helpers for the CloudSC-variants numerical-correctness harness.

* ``emit_and_compile_native`` -- run the NumpyToX translators on a numpy
  reference + bench_info, then compile the emitted C / C++ / Fortran into
  three shared libraries (one ABI, three back-ends).
* ``call_native`` -- drive one of those .so's through ctypes using its
  ``*_binding.json`` (arg order + kinds), passing C-contiguous buffers.
* ``compare`` -- max-abs / max-rel error report against the numpy oracle.
"""
import ctypes
import json
import os
import subprocess
import numpy as np

TRANSLATORS_SRC = "/home/primrose/Work/npbench/npbench/NumpyTranslators/src"
# The translators were developed under py12; pin their interpreter so the
# emit step is independent of whichever env runs the harness (py13/FaCe).
PY12 = "/home/primrose/.pyenv/versions/py12/bin/python"

_GCC = ["gcc", "-O3", "-march=native", "-ffast-math", "-std=c17", "-shared", "-fPIC"]
_GXX = ["g++", "-O3", "-march=native", "-ffast-math", "-std=c++17", "-shared", "-fPIC"]
_GFORT = ["gfortran", "-O3", "-march=native", "-ffast-math", "-fno-math-errno", "-shared", "-fPIC"]
# -ffast-math + -march=native auto-vectorise tight exp/log loops into libmvec
# calls (e.g. _ZGVbN2v_exp); link the scalar + vector math libs so the .so
# resolves them at dlopen time.
_LIBS = ["-lm", "-lmvec"]


def emit_and_compile_native(kernel_dir, stem, numpy_py, bench_info, out="gen"):
    """Emit + compile C / C++ / Fortran. Returns {lang: (so_path, binding)}."""
    gen = os.path.join(kernel_dir, out)
    os.makedirs(gen, exist_ok=True)
    env = dict(os.environ, PYTHONPATH=TRANSLATORS_SRC)
    for target in ("c", "fortran"):
        subprocess.run(
            [PY12, "-m", "numpyto_common.cli", "--target", target,
             "--kernel", os.path.join(kernel_dir, numpy_py),
             "--bench-info", os.path.join(kernel_dir, bench_info),
             "--out", gen],
            check=True, env=env, capture_output=True, text=True)

    base = f"{stem}_fp64"
    binding = json.load(open(os.path.join(gen, f"{base}_binding.json")))
    srcs = {"c": (_GCC, f"{base}.c"), "cpp": (_GXX, f"{base}.cpp"), "fortran": (_GFORT, f"{base}.f90")}
    out_map = {}
    for lang, (cc, src) in srcs.items():
        so = os.path.join(gen, f"lib{stem}_{lang}.so")
        subprocess.run(cc + [os.path.join(gen, src), "-o", so] + _LIBS, check=True,
                       capture_output=True, text=True)
        out_map[lang] = (so, binding)
    return out_map


def call_native(so_path, binding, env, arrays):
    """Call a NumpyToX .so. ``env`` maps scalar/symbol names -> values;
    ``arrays`` maps array names -> C-contiguous float64 ndarrays (mutated
    in place for outputs). Returns elapsed ns reported by the kernel."""
    lib = ctypes.CDLL(so_path)
    fn = getattr(lib, binding["symbols"]["c"])
    fn.restype = None
    cargs, argtypes = [], []
    for a in binding["args"]:
        nm, kind = a["name"], a["kind"]
        if kind.startswith("ptr_"):
            buf = arrays[nm]
            cargs.append(buf.ctypes.data_as(ctypes.c_void_p))
            argtypes.append(ctypes.c_void_p)
        elif kind == "int64":
            cargs.append(ctypes.c_int64(int(env[nm])))
            argtypes.append(ctypes.c_int64)
        elif kind == "double":
            cargs.append(ctypes.c_double(float(env[nm])))
            argtypes.append(ctypes.c_double)
        elif kind == "float":
            cargs.append(ctypes.c_float(float(env[nm])))
            argtypes.append(ctypes.c_float)
        else:
            raise ValueError(f"unhandled kind {kind!r} for {nm!r}")
    timing = np.zeros(1, dtype=np.int64)
    cargs.append(timing.ctypes.data_as(ctypes.c_void_p))
    argtypes.append(ctypes.c_void_p)
    fn.argtypes = argtypes
    fn(*cargs)
    return int(timing[0])


def compare(label, ref, got, rtol=1e-9, atol=1e-12):
    """Return (ok, msg) comparing each output array ref[k] vs got[k]."""
    worst = 0.0
    details = []
    for k in ref:
        r = np.asarray(ref[k], dtype=np.float64)
        g = np.asarray(got[k], dtype=np.float64)
        if r.shape != g.shape:
            return False, f"{label}: shape mismatch {k} {r.shape} vs {g.shape}"
        denom = np.maximum(np.abs(r), atol)
        rel = np.abs(r - g) / denom
        m = float(np.max(rel)) if rel.size else 0.0
        worst = max(worst, m)
        details.append(f"{k}:maxrel={m:.2e}")
    ok = bool(np.isfinite(worst) and worst <= rtol)
    status = "PASS" if ok else "FAIL"
    return ok, f"[{status}] {label:28s} worst_rel={worst:.2e}  ({', '.join(details)})"
