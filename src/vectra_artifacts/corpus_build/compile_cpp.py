"""
compile_cpp.py  —  src/vectra_artifacts/corpus_build/compile_cpp.py

Compile per-kernel .cpp files into a single shared library.
Walks a microkernels/cpp root for .cpp files, compiles each to .o with
header-aware dependency tracking, then links them all into one .so.
Shared by tsvc_2 and tsvc_2_5.
"""

import argparse
import ctypes
import os
import pathlib
import re
import statistics
import subprocess
import sys
import time as _time
from typing import List, Optional
import numpy as np

# ---------------------------------------------------------------------------
# Compiler config (graceful fallback if compiler_config is not importable)
# ---------------------------------------------------------------------------
try:
    from compiler_config import CXX, COMPILE_FLAGS, LINK_FLAGS  # type: ignore
except ImportError:
    CXX           = os.environ.get("CXX", "clang++")
    COMPILE_FLAGS = ["-O3", "-std=c++17", "-fPIC", "-march=native"]
    LINK_FLAGS    = ["-shared"]


# ---------------------------------------------------------------------------
# ctypes shorthands — NOTE: named with leading underscore so pickle can find
# them via the module dict when spawn context is used.
# ---------------------------------------------------------------------------
_dp   = ctypes.POINTER(ctypes.c_double)
_fp   = ctypes.POINTER(ctypes.c_float)
_ip   = ctypes.POINTER(ctypes.c_int)
_i64p = ctypes.POINTER(ctypes.c_int64)
_int  = ctypes.c_int
_dbl  = ctypes.c_double
_flt  = ctypes.c_float

# Serialisable string tags used to transfer sig info across process boundaries
_TAG_TO_CTYPE = {
    "dp":   _dp,
    "fp":   _fp,
    "ip":   _ip,
    "i64p": _i64p,
    "int":  _int,
    "dbl":  _dbl,
    "flt":  _flt,
}

def _ctype_tag(ct) -> str:
    """Return a string tag for a ctypes type so it survives pickling."""
    for tag, v in _TAG_TO_CTYPE.items():
        if ct is v:
            return tag
    # Fallback: map by name
    name = getattr(ct, "__name__", "") or ""
    if "double" in name and "LP" in name:   return "dp"
    if "float"  in name and "LP" in name:   return "fp"
    if "int64"  in name and "LP" in name:   return "i64p"
    if "int"    in name and "LP" in name:   return "ip"
    if "double" in name:                    return "dbl"
    if "float"  in name:                    return "flt"
    return "int"

def _serialise_sig(sig) -> list:
    """Convert [(name, c_typed, c_typef), ...] to [(name, tag_d, tag_f), ...].
    These plain tuples of strings are safely picklable."""
    return [(name, _ctype_tag(c_typed), _ctype_tag(c_typef)) for name, c_typed, c_typef in sig]

def _to_carg(val, tag: str, is_float: bool):
    import numpy as np
    ct = _TAG_TO_CTYPE[tag]
    if isinstance(val, np.ndarray):
        if ct is _i64p:
            return val.astype(np.int64, copy=False).ctypes.data_as(_i64p)
        if is_float and val.dtype == np.float64:
            val = val.astype(np.float32)
        elif not is_float and val.dtype == np.float32:
            val = val.astype(np.float64)
        if ct is _ip:
            return val.astype("int32", copy=False).ctypes.data_as(_ip)
        return val.ctypes.data_as(_fp if is_float else _dp)
    if ct is _int:
        return _int(int(val))
    if ct in (_dbl, _flt):
        return _flt(float(val)) if is_float else _dbl(float(val))
    return val


def _build_call_args(serial_sig: list, pool: dict, is_float: bool):
    """Walk a serialised signature and resolve each param from pool.
    Returns (call_args, missing_param_names)."""
    call_args: list = []
    missing:   list = []
    for param_name, tag_d, tag_f in serial_sig:
        tag = tag_f if is_float else tag_d
        if param_name not in pool:
            missing.append(param_name)
            continue
        call_args.append(_to_carg(pool[param_name], tag, is_float))
    return call_args, missing


# ---------------------------------------------------------------------------
# Incremental-build helpers
# ---------------------------------------------------------------------------

def obj_path(src: pathlib.Path, build_dir: pathlib.Path) -> pathlib.Path:
    return build_dir / f"{src.stem}.o"

def dep_path(obj: pathlib.Path) -> pathlib.Path:
    return obj.with_suffix(".d")

def parse_dep_file(dep: pathlib.Path) -> List[pathlib.Path]:
    if not dep.exists():
        return []
    _, _, rhs = dep.read_text().partition(":")
    rhs = rhs.replace("\\", " ")
    return [pathlib.Path(p) for p in rhs.split() if p]

def needs_rebuild(src: pathlib.Path, obj: pathlib.Path) -> bool:
    if not obj.exists():
        return True
    obj_mtime = obj.stat().st_mtime
    deps = parse_dep_file(dep_path(obj))
    if deps:
        for dep in deps:
            try:
                if dep.stat().st_mtime > obj_mtime:
                    return True
            except FileNotFoundError:
                return True
        return False
    return src.stat().st_mtime > obj_mtime


# ---------------------------------------------------------------------------
# Vectorization-report helpers
# ---------------------------------------------------------------------------

VECRE = re.compile(
    r"optimized loop vectorized"
    r"|vectorized loop"
    r"|LOOP AUTO-VECTORIZED",
    re.IGNORECASE,
)

def vec_report_flag() -> List[str]:
    cxx = CXX.lower()
    if "clang" in cxx:
        return ["-Rpass=loop-vectorize", "-Rpass-missed=loop-vectorize"]
    if "icpx" in cxx or "icpc" in cxx:
        return ["-qopt-report=2", "-qopt-report-phase=vec"]
    return ["-fopt-info-vec-all"]

def parse_vec_reports(build_dir) -> dict:
    build_dir = pathlib.Path(build_dir)
    results: dict = {}
    for rpt in sorted(build_dir.rglob("*.rpt")):
        kernel = re.sub(r"[df](single)?$", "", rpt.stem, flags=re.IGNORECASE)
        text   = rpt.read_text(errors="replace")
        results[kernel] = results.get(kernel, False) or bool(VECRE.search(text))
    return results


# ---------------------------------------------------------------------------
# Compile / link
# ---------------------------------------------------------------------------

def compile_object(
    src,
    build_dir,
    extra_flags: Optional[List[str]] = None,
    force: bool = False,
    vec_report: bool = False,
) -> pathlib.Path:
    src       = pathlib.Path(src).resolve()
    build_dir = pathlib.Path(build_dir).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    obj = obj_path(src, build_dir)

    if not force and not needs_rebuild(src, obj):
        return obj

    flags = list(COMPILE_FLAGS)
    if extra_flags:
        flags.extend(extra_flags)
    if vec_report:
        flags.extend(vec_report_flag())

    result = subprocess.run(
        [CXX, "-c", *flags, str(src), "-o", str(obj)],
        stderr=subprocess.PIPE, text=True,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, result.args, stderr=result.stderr)
    if vec_report:
        obj.with_suffix(".rpt").write_text(result.stderr)
    return obj


def link_library(
    objects: List[pathlib.Path],
    build_dir,
    so_name: str,
    extra_link_flags: Optional[List[str]] = None,
) -> pathlib.Path:
    build_dir = pathlib.Path(build_dir).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    so    = build_dir / so_name
    flags = list(LINK_FLAGS)
    if extra_link_flags:
        flags.extend(extra_link_flags)
    subprocess.check_call([CXX, *flags, *[str(o) for o in objects], "-o", str(so)])
    return so


def compile_library(
    root,
    build_dir,
    so_name: str,
    extra_flags: Optional[List[str]] = None,
    extra_link_flags: Optional[List[str]] = None,
    force: bool = False,
    pattern: str = "*.cpp",
    jobs: int = 1,
    vec_report: bool = False,
) -> pathlib.Path:
    """Compile every kernel under *root* and link them into one .so."""
    root = pathlib.Path(root).resolve()
    cpps = sorted(root.rglob(pattern))

    if jobs > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        objects: List[pathlib.Path] = []
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futs = {
                pool.submit(compile_object, cpp, build_dir, extra_flags, force, vec_report): cpp
                for cpp in cpps
            }
            for fut in as_completed(futs):
                cpp = futs[fut]
                try:
                    objects.append(fut.result())
                except subprocess.CalledProcessError as e:
                    print(f"FAIL {cpp.name}: {e}")
    else:
        objects = [
            compile_object(cpp, build_dir, extra_flags, force, vec_report)
            for cpp in cpps
        ]
    return link_library(objects, build_dir, so_name, extra_link_flags)


# Alias so that __init__.py `from .compile_cpp import compile_cpp_library` keeps working
compile_cpp_library = compile_library


def load_cpp_library(root, build_dir, so_name: str, **kwargs) -> ctypes.CDLL:
    so = compile_library(root, build_dir, so_name, **kwargs)
    return ctypes.CDLL(str(so))


# ---------------------------------------------------------------------------
# Array pool
# ---------------------------------------------------------------------------

def _make_array_pool(len_1d: int, dtype):
    import numpy as np
    rng  = np.random.default_rng(42)
    n_2d = len_1d * len_1d

    SSYM   = 4
    dim_2d  = min(len_1d, 4096)
    dim_3d  = 32
    arr_3d  = rng.random((dim_3d, dim_3d, dim_3d)).astype(dtype)
    idx_arr = np.mod(np.arange(len_1d, dtype=np.int64) * 7 + 3, len_1d)
    return {
        # 1-D float arrays
        "a":             rng.random(len_1d).astype(dtype),
        "b":             rng.random(len_1d).astype(dtype),
        "c":             rng.random(len_1d).astype(dtype),
        "d":             rng.random(len_1d).astype(dtype),
        "e":             rng.random(len_1d).astype(dtype),
        "q":             rng.random(len_1d).astype(dtype),
        "x":             rng.random(len_1d).astype(dtype),
        "xx":            rng.random(len_1d).astype(dtype),
        "y":             rng.random(len_1d).astype(dtype),
        "z":             rng.random(len_1d).astype(dtype),
        "out":           np.zeros(len_1d, dtype=dtype),
        # 2-D (flattened)
        "aa":            rng.random(n_2d).astype(dtype),
        "bb":            rng.random(n_2d).astype(dtype),
        "cc":            rng.random(n_2d).astype(dtype),
        "dd":            rng.random(n_2d).astype(dtype),
        "flat":          rng.random(len_1d).astype(dtype),
        "flat_2d_array": rng.random(n_2d).astype(dtype),
        # integer index arrays
        "ip":            rng.integers(0, len_1d, size=len_1d).astype("int32"),
        "indx":          rng.integers(0, len_1d, size=len_1d).astype("int32"),
        # reduction outputs
        "sumout":    np.zeros(1, dtype=dtype),
        "result":    np.zeros(1, dtype=dtype),
        "resultout": np.zeros(1, dtype=dtype),
        "dot":       np.zeros(1, dtype=dtype),
        "dotout":    np.zeros(1, dtype=dtype),
        # integer scalars
        "iterations": len_1d,
        "len_1d":     len_1d,
        "len_2d":     len_1d,
        "LEN_1D":     len_1d,
        "LEN_2D": dim_2d, 
        "LEN_3D": dim_3d,
        "len_3d": dim_3d,
        "ntimes": len_1d,
        "iterations": len_1d,
        "n1":         len_1d // 4,
        "n3":         len_1d // 4,
        "inc":        1,
        "k":          0,
        "j":          0,
        "vlen":       8,
        "M":          len_1d // 2,
        "m": len_1d,
        "threshold":  0,
        "sum_out": np.zeros(1, dtype=dtype),
        "dot_out": np.zeros(1, dtype=dtype),
        "result_out": np.zeros(1, dtype=dtype),
        # float scalars
        "s":     1.0,
        "s1":    1.0,
        "s2":    2.0,
        "scale": 1.0,
        "ssym":  3,
        # tsvc_2_5
        "src": rng.random(len_1d).astype(dtype),
        "dst": rng.random(SSYM * len_1d).astype(dtype),
        "idx": idx_arr.copy(),
        "threshold_data": rng.random(len_1d).astype(dtype),
        "mask": rng.integers(0, 2, size=len_1d, dtype=np.int64),
        "t": 1.0,
        "a_3d": arr_3d.ravel(), "b_3d": arr_3d.ravel().copy(),
        # jacobi2d_double_tiled_sym_d: two symbolic tile sizes
        "t1": 64,
        "t2": 8,
    }


# ---------------------------------------------------------------------------
# Signature / bindings loader
# ---------------------------------------------------------------------------

def _load_signatures(root: pathlib.Path, so_path: pathlib.Path):
    """Infer the correct bindings file from 'tsvc_2_5' or 'tsvc_2' in root."""
    import importlib.util

    root_str = str(root)

    # Check tsvc_2_5 first — it must come before tsvc_2 because tsvc_2_5
    # also contains the substring "tsvc_2".
    if "tsvc_2_5" in root_str:
        bindings_rel = "tsvc_2_5/tsvc_2_5_bindings.py"
    elif "tsvc_2" in root_str:
        bindings_rel = "tsvc_2/tsvc_bindings.py"
    else:
        print(f"  [timing] ERROR: cannot infer TSVC version from root path: {root}",
              flush=True)
        return None

    # Anchor the bindings file relative to cwd (where the user runs the script from)
    bindings_path = pathlib.Path.cwd() / bindings_rel

    if not bindings_path.exists():
        print(f"  [timing] ERROR: bindings file not found: {bindings_path}", flush=True)
        return None

    spec = importlib.util.spec_from_file_location("_tsvc_bindings_tmp", bindings_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    sigs = getattr(mod, "SIGNATURES", None)

    if not sigs:
        print(f"  [timing] ERROR: no SIGNATURES found in {bindings_path}", flush=True)
        return None

    print(f"  location of signature to load:  {bindings_path}", flush=True)
    return sigs


def infer_precision_from_pattern(pattern: str) -> str:
    if "f" in pattern.lower() and "d" not in pattern.lower():
        return "float"
    return "double"


# ---------------------------------------------------------------------------
# Per-kernel debug child  (subprocess-isolated, mirrors DaCe version)
# Accepts only plain-Python picklable args: strings, dicts of numpy arrays
# and plain ints/floats — no ctypes types.
# ---------------------------------------------------------------------------

def _run_one_kernel_child(so_path_str: str, sym: str,
                          serial_sig: list, pool: dict,
                          is_float: bool, reps: int,
                          verbose: bool = False):
    """
    Runs inside a forked/spawned child process.  Times the kernel *reps* times.
    Diagnostic output is gated behind *verbose* (only set when --debug-kernel is used).
    serial_sig is a list of (param_name, tag_d, tag_f) — plain strings, always picklable.
    """
    import numpy as np

    if verbose:
        sig_desc  = ", ".join(f"{n}, {(tf if is_float else td)}"
                              for n, td, tf in serial_sig)
        pool_keys = ", ".join(n for n, *_ in serial_sig if n in pool)
        print(f"child sig:          {sig_desc}", flush=True)
        print(f"child pool keys:    {pool_keys}", flush=True)

    call_args, missing = _build_call_args(serial_sig, pool, is_float)
    if missing:
        if verbose:
            print(f"UNRESOLVED: {', '.join(missing)}", flush=True)
        sys.exit(2)

    if verbose:
        print(f"child callargs types: {', '.join(type(a).__name__ for a in call_args)}",
              flush=True)

    try:
        lib = ctypes.CDLL(so_path_str, ctypes.RTLD_GLOBAL)
    except OSError as exc:
        print(f"LOAD ERROR: {exc}", flush=True)
        sys.exit(3)

    try:
        fn = getattr(lib, sym)
    except AttributeError:
        print(f"SYMBOL NOT FOUND: {sym}", flush=True)
        sys.exit(4)

    fn.restype = None

    timens_buf = np.zeros(1, dtype=np.int64)
    timens_ptr = timens_buf.ctypes.data_as(_i64p)
    timings    = []
    for _ in range(reps):
        fn(*call_args, timens_ptr)
        timings.append(int(timens_buf[0]))

    med = statistics.median(timings)
    mn  = min(timings)
    sd  = statistics.stdev(timings) if len(timings) > 1 else 0.0
    if verbose:
        print(f"OK median={med:.0f}ns min={mn:.0f}ns stdev={sd:.0f}ns", flush=True)
    sys.exit(0)


# ---------------------------------------------------------------------------
# Timing phase
# ---------------------------------------------------------------------------

def run_timing_phase(
    so_path: pathlib.Path,
    signatures,
    out_csv: pathlib.Path,
    pattern: str,
    reps: int,
    len_1d: int,
    debug_kernel: Optional[str] = None,
) -> None:
    """
    Load the compiled .so and time every kernel in *signatures*.
    Each kernel is probed in an isolated subprocess first so a SIGSEGV
    cannot crash the parent.  Uses 'fork' on macOS/Linux (no pickle needed);
    falls back to 'spawn' with fully picklable serialised signatures.
    """
    import csv
    import multiprocessing as mp
    import numpy as np

    so_path  = pathlib.Path(so_path)
    out_csv  = pathlib.Path(out_csv)
    is_float = infer_precision_from_pattern(pattern) == "float"
    dtype    = np.float32 if is_float else np.float64
    suffix   = "f" if is_float else "d"
    sym_suffix = f"_{suffix}_single" if "single" in pattern else f"_{suffix}"

    pool = _make_array_pool(len_1d, dtype)

    # Prefer 'fork' — no pickle needed, much faster startup
    mp_ctx_name = "fork" if sys.platform != "win32" else "spawn"
    ctx = mp.get_context(mp_ctx_name)

    print(f"  [timing] Using SIGNATURES ({len(signatures)} kernels)", flush=True)

    # ---- single-kernel debug mode ----
    if debug_kernel:
        base = re.sub(r"[_]?[df](single)?$", "", debug_kernel)
        sig  = signatures.get(base) or signatures.get(debug_kernel)
        if sig is None:
            print(f"  [debug] '{debug_kernel}' not found in SIGNATURES. "
                  f"Sample keys: {list(signatures)[:6]}", flush=True)
            return
        sym        = f"{base}{sym_suffix}"
        serial_sig = _serialise_sig(sig)
        _run_one_kernel_child(str(so_path), sym, serial_sig, pool, is_float, reps,
                              verbose=True)
        return

    # ---- full sweep ----
    n_timed = n_skipped = n_crashed = 0
    rows: list = []

    # Pre-load .so once for the in-process timing after the subprocess probe passes
    try:
        lib = ctypes.CDLL(str(so_path), ctypes.RTLD_GLOBAL)
    except OSError as exc:
        print(f"  [timing] Cannot load {so_path}: {exc}", flush=True)
        return

    for base, sig in sorted(signatures.items()):
        sym        = f"{base}{sym_suffix}"
        serial_sig = _serialise_sig(sig)
        print(f"  [timing] running {sym} ...", end=" ", flush=True)

        # Quick Python-side unresolved check
        _, missing = _build_call_args(serial_sig, pool, is_float)
        if missing:
            print(f"SKIP — unresolved args: {', '.join(missing)}", flush=True)
            n_skipped += 1
            continue

        # Subprocess probe — catches SIGSEGV without killing parent
        proc = ctx.Process(target=_run_one_kernel_child,
                           args=(str(so_path), sym, serial_sig, pool, is_float, 1, False),
                           daemon=True)
        proc.start()
        proc.join(timeout=30)
        ec = proc.exitcode

        if ec == 2:
            print("SKIP (unresolved args in child)", flush=True)
            n_skipped += 1
            continue
        if ec != 0:
            print(f"CRASH exit {ec}", flush=True)
            if debug_kernel is not None:
                call_args2, _ = _build_call_args(serial_sig, pool, is_float)
                sig_desc   = [(n, tf if is_float else td) for n, td, tf in serial_sig]
                pool_keys  = [n for n, *_ in serial_sig if n in pool]
                call_types = [type(a).__name__ for a in call_args2]
                print(f"    child sig:            {sig_desc}", flush=True)
                print(f"    child pool keys:      {pool_keys}", flush=True)
                print(f"    child callargs types: {call_types}", flush=True)
            n_crashed += 1
            continue

        # Subprocess probe passed → safe to time in-process
        try:
            fn = getattr(lib, sym)
            fn.restype = None

            call_args, _ = _build_call_args(serial_sig, pool, is_float)
            timens_buf   = np.zeros(1, dtype=np.int64)
            timens_ptr   = timens_buf.ctypes.data_as(_i64p)
            timings      = []
            for _ in range(reps):
                fn(*call_args, timens_ptr)
                timings.append(int(timens_buf[0]))

            med = statistics.median(timings)
            mn  = min(timings)
            sd  = statistics.stdev(timings) if len(timings) > 1 else 0.0
            print(f"ok  median={med/1e3:.1f}µs  min={mn/1e3:.1f}µs", flush=True)
            rows.append({"kernel": sym,
                         "median_ns": f"{med:.0f}",
                         "min_ns":    f"{mn:.0f}",
                         "stdev_ns":  f"{sd:.0f}"})
            n_timed += 1
        except Exception as exc:
            if debug_kernel is not None:
                print(f"CRASH (in-process): {exc}", flush=True)
            else:
                print(f"CRASH", flush=True)
            n_crashed += 1

    # Write CSV
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["kernel","median_ns","min_ns","stdev_ns"])
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"  [timing] {n_timed} kernels timed, "
        f"{n_skipped} skipped, {n_crashed} crashed"
        f" -> {out_csv}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# main_compile_cpp  — argparse entry point called by tsvc_2 / tsvc_2_5
# ---------------------------------------------------------------------------

def main_compile_cpp(
    default_root: str,
    default_build_dir: str,
    default_so_name: str,
    argv: list = None,
) -> int:

    ap = argparse.ArgumentParser(
        description="Compile per-kernel .cpp files into a single shared library."
    )
    ap.add_argument("root",              nargs="?", default=default_root,
                    help="Root directory of kernel sources.")
    ap.add_argument("-b", "--build-dir",           default=default_build_dir)
    ap.add_argument("-o", "--so-name",             default=default_so_name)
    ap.add_argument("-f", "--force",  action="store_true")
    ap.add_argument("-j", "--jobs",   type=int,    default=os.cpu_count())
    ap.add_argument("--pattern",                   default="*.cpp")
    ap.add_argument("--vec-report",   action="store_true",
                    help="Capture vectorization remarks into build_dir/*.rpt files.")
    ap.add_argument("--vec-report-out", default=None, metavar="FILE",
                    help="Write vec-report summary to FILE.")
    # Timing flags
    ap.add_argument("--time",         action="store_true",
                    help="After linking, load the .so and time every kernel.")
    ap.add_argument("--timing-out",   default=None, metavar="FILE",
                    help="Write timing CSV to FILE.")
    ap.add_argument("--reps",         type=int, default=30, metavar="N",
                    help="Timing repetitions per kernel (default 30).")
    ap.add_argument("--len-1d",       type=int, default=1024, metavar="N",
                    dest="len_1d",
                    help="Array length used during timing (default 1024).")
    # Debug single kernel — mirrors DaCe --debug-kernel
    ap.add_argument("--debug-kernel", default=None, metavar="NAME",
                    help="Run only this one kernel with full verbose child diagnostics.")

    args = ap.parse_args(argv)
    if args.debug_kernel:
        args.time = True

    build_dir = pathlib.Path(args.build_dir).resolve()
    root      = pathlib.Path(args.root).resolve()
    cpps      = sorted(root.rglob(args.pattern))
    print(f"Found {len(cpps)} source files under {root}", flush=True)

    t0 = _time.perf_counter()

    # ---- compile ----
    if args.jobs > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        objects: List[pathlib.Path] = []
        compiled = cached = 0
        with ThreadPoolExecutor(max_workers=args.jobs) as tpool:
            futs = {
                tpool.submit(
                    compile_object, cpp, args.build_dir,
                    force=args.force, vec_report=args.vec_report
                ): cpp
                for cpp in cpps
            }
            for fut in as_completed(futs):
                cpp = futs[fut]
                try:
                    obj = fut.result()
                    objects.append(obj)
                    compiled += 1
                except subprocess.CalledProcessError as e:
                    print(f"FAIL {cpp.name}: {e}")
                    compiled += 1
        print(f"Compile {compiled} compiled, {cached} cached", flush=True)
    else:
        objects = [
            compile_object(cpp, args.build_dir,
                           force=args.force, vec_report=args.vec_report)
            for cpp in cpps
        ]

    so = link_library(objects, args.build_dir, args.so_name)
    print(f"Linked {len(objects)} objects -> {so}", flush=True)

    # ---- vec report ----
    if args.vec_report:
        results = parse_vec_reports(args.build_dir)
        if results:
            vec_count   = sum(1 for v in results.values() if v)
            header      = f"Vectorization report {vec_count}/{len(results)} kernels vectorized"
            lines       = [header]
            for name, vec in sorted(results.items()):
                lines.append(f"  {'VEC' if vec else '---'}  {name}")
            report_text = "\n".join(lines)
            print(report_text)

            out_rpt = (
                pathlib.Path(args.vec_report_out) if args.vec_report_out
                else build_dir / f"{pathlib.Path(args.so_name).stem}.vecreport.txt"
            )
            out_rpt.parent.mkdir(parents=True, exist_ok=True)
            out_rpt.write_text(report_text)
            print(f"Saved vec report -> {out_rpt}", flush=True)
        else:
            print("vec-report: No .rpt files found — recompile to generate them.",
                  flush=True)

    # ---- timing phase ----
    if args.time:
        timing_out = (
            pathlib.Path(args.timing_out) if args.timing_out
            else build_dir / f"{pathlib.Path(args.so_name).stem}.timing_report.csv"
        )
        signatures = _load_signatures(root, so)
        if signatures is None:
            print("  [timing] WARNING: could not locate tsvc_*_bindings.py — "
                  "timing phase skipped.", flush=True)
        else:
            print(
                f"  Running timing phase ({args.reps} reps, len_1d={args.len_1d}) ...",
                flush=True,
            )
            run_timing_phase(
                so_path      = so,
                signatures   = signatures,
                out_csv      = timing_out,
                pattern      = args.pattern,
                reps         = args.reps,
                len_1d       = args.len_1d,
                debug_kernel = args.debug_kernel,
            )

    print(f"Done in {_time.perf_counter() - t0:.1f}s", flush=True)
    return 0