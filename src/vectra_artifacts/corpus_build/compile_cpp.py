#!/usr/bin/env python3
"""
compile_cpp.py  —  src/vectra_artifacts/corpus_build/compile_cpp.py

Compile per-kernel .cpp files into a single shared library.
Walks a microkernels/cpp root for .cpp files, compiles each to .o with
header-aware dependency tracking, then links them all into one .so.
Shared by tsvc_2 and tsvc_2_5.
"""

import argparse
import ctypes
import multiprocessing
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
# ctypes shorthands
# ---------------------------------------------------------------------------
_dp   = ctypes.POINTER(ctypes.c_double)
_fp   = ctypes.POINTER(ctypes.c_float)
_ip   = ctypes.POINTER(ctypes.c_int)
_i64p = ctypes.POINTER(ctypes.c_int64)
_int  = ctypes.c_int
_dbl  = ctypes.c_double
_flt  = ctypes.c_float

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
    for tag, v in _TAG_TO_CTYPE.items():
        if ct is v:
            return tag
    name = getattr(ct, "__name__", "") or ""
    if "double" in name and "LP" in name:   return "dp"
    if "float"  in name and "LP" in name:   return "fp"
    if "int64"  in name and "LP" in name:   return "i64p"
    if "int"    in name and "LP" in name:   return "ip"
    if "double" in name:                    return "dbl"
    if "float"  in name:                    return "flt"
    return "int"


def _serialise_sig(sig) -> list:
    return [(name, _ctype_tag(c_typed), _ctype_tag(c_typef))
            for name, c_typed, c_typef in sig]


def _to_carg(val, tag: str, is_float: bool):
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
_VEC_OPTIMIZED_RE = re.compile(
    r"remark.*vectorized loop"
    r"|note.*loop vectorized"
    r"|optimized.*loop vectorized"
    r"|note.*vectorized (?!0\b)\d+ loop"
    r"|LOOP AUTO-VECTORIZED"
    r"|loop vectorized",
    re.IGNORECASE,
)
_VEC_MISSED_RE = re.compile(
    r"remark.*loop not vectorized"
    r"|missed.*loop"
    r"|couldn.t vectorize"
    r"|not vectorized"
    r"|missed:.*loop",
    re.IGNORECASE,
)

VECRE = _VEC_OPTIMIZED_RE


def _parse_vec_from_rpt(rpt_path: pathlib.Path) -> dict:
    if not rpt_path.exists():
        return {"vectorized": False, "vec_count": 0, "missed_count": 0, "sample_remarks": []}
    text = rpt_path.read_text(errors="replace")
    vec_lines    = [l.strip() for l in text.splitlines() if _VEC_OPTIMIZED_RE.search(l)]
    missed_lines = [l.strip() for l in text.splitlines() if _VEC_MISSED_RE.search(l)]
    return {
        "vectorized":     len(vec_lines) > 0,
        "vec_count":      len(vec_lines),
        "missed_count":   len(missed_lines),
        "sample_remarks": (vec_lines + missed_lines)[:5],
    }


def vec_report_flag() -> List[str]:
    cxx = CXX.lower()
    if "clang" in cxx:
        return [
            "-Rpass=loop-vectorize",
            "-Rpass-missed=loop-vectorize",
            "-Rpass-analysis=loop-vectorize",
        ]
    if "icpx" in cxx or "icpc" in cxx:
        return [
            "-Rpass=loop-vectorize",
            "-Rpass-missed=loop-vectorize",
            "-Rpass-analysis=loop-vectorize",
        ]
    return ["-fopt-info-vec-all"]


def parse_vec_reports(build_dir) -> dict:
    build_dir = pathlib.Path(build_dir)
    results: dict = {}
    for rpt in sorted(build_dir.rglob("*.rpt")):
        kernel = re.sub(r"_[df](_single)?$", "", rpt.stem, flags=re.IGNORECASE)
        text   = rpt.read_text(errors="replace")
        results[kernel] = results.get(kernel, False) or bool(_VEC_OPTIMIZED_RE.search(text))
    return results


def parse_vec_reports_detailed(build_dir) -> dict:
    build_dir = pathlib.Path(build_dir)
    results: dict = {}
    for rpt in sorted(build_dir.rglob("*.rpt")):
        kernel = re.sub(r"_[df](_single)?$", "", rpt.stem, flags=re.IGNORECASE)
        info   = _parse_vec_from_rpt(rpt)
        if kernel not in results:
            results[kernel] = info
        else:
            existing = results[kernel]
            results[kernel] = {
                "vectorized":     existing["vectorized"] or info["vectorized"],
                "vec_count":      existing["vec_count"]  + info["vec_count"],
                "missed_count":   existing["missed_count"] + info["missed_count"],
                "sample_remarks": (existing["sample_remarks"] + info["sample_remarks"])[:5],
            }
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


compile_cpp_library = compile_library


def load_cpp_library(root, build_dir, so_name: str, **kwargs) -> ctypes.CDLL:
    so = compile_library(root, build_dir, so_name, **kwargs)
    return ctypes.CDLL(str(so))

# ---------------------------------------------------------------------------
# Array pool
# ---------------------------------------------------------------------------

def _make_array_pool(len_1d: int, dtype):
    rng     = np.random.default_rng(42)
    n_2d    = len_1d * len_1d
    SSYM    = 4
    dim_2d  = min(len_1d, 4096)
    dim_3d  = 32
    arr_3d  = rng.random((dim_3d, dim_3d, dim_3d)).astype(dtype)
    idx_arr = np.mod(np.arange(len_1d, dtype=np.int64) * 7 + 3, len_1d)
    return {
        "a":              rng.random(len_1d).astype(dtype),
        "b":              rng.random(len_1d).astype(dtype),
        "c":              rng.random(len_1d).astype(dtype),
        "d":              rng.random(len_1d).astype(dtype),
        "e":              rng.random(len_1d).astype(dtype),
        "q":              rng.random(len_1d).astype(dtype),
        "x":              rng.random(len_1d).astype(dtype),
        "xx":             rng.random(len_1d).astype(dtype),
        "y":              rng.random(len_1d).astype(dtype),
        "z":              rng.random(len_1d).astype(dtype),
        "out":            np.zeros(len_1d, dtype=dtype),
        "aa":             rng.random(n_2d).astype(dtype),
        "bb":             rng.random(n_2d).astype(dtype),
        "cc":             rng.random(n_2d).astype(dtype),
        "dd":             rng.random(n_2d).astype(dtype),
        "flat":           rng.random(len_1d).astype(dtype),
        "flat_2d_array":  rng.random(n_2d).astype(dtype),
        "ip":             rng.integers(0, len_1d, size=len_1d).astype("int32"),
        "indx":           rng.integers(0, len_1d, size=len_1d).astype("int32"),
        "sumout":         np.zeros(1, dtype=dtype),
        "result":         np.zeros(1, dtype=dtype),
        "resultout":      np.zeros(1, dtype=dtype),
        "dot":            np.zeros(1, dtype=dtype),
        "dotout":         np.zeros(1, dtype=dtype),
        "iterations":     len_1d,
        "len_1d":         len_1d,
        "len_2d":         len_1d,
        "LEN_1D":         len_1d,
        "LEN_2D":         dim_2d,
        "LEN_3D":         dim_3d,
        "len_3d":         dim_3d,
        "ntimes":         len_1d,
        "n1":             len_1d // 4,
        "n3":             len_1d // 4,
        "inc":            1,
        "k":              0,
        "j":              0,
        "vlen":           8,
        "M":              len_1d // 2,
        "m":              len_1d,
        "threshold":      0,
        "sum_out":        np.zeros(1, dtype=dtype),
        "dot_out":        np.zeros(1, dtype=dtype),
        "result_out":     np.zeros(1, dtype=dtype),
        "s":              1.0,
        "s1":             1.0,
        "s2":             2.0,
        "scale":          1.0,
        "ssym":           3,
        "src":            rng.random(len_1d).astype(dtype),
        "dst":            rng.random(SSYM * len_1d).astype(dtype),
        "idx":            idx_arr.copy(),
        "threshold_data": rng.random(len_1d).astype(dtype),
        "mask":           rng.integers(0, 2, size=len_1d, dtype=np.int64),
        "t":              1.0,
        "a_3d":           arr_3d.ravel(),
        "b_3d":           arr_3d.ravel().copy(),
        "t1":             64,
        "t2":             8,
    }

# ---------------------------------------------------------------------------
# Signature / bindings loader
# ---------------------------------------------------------------------------

def _load_signatures(root: pathlib.Path, so_path: pathlib.Path):
    import importlib.util
    root_str = str(root)
    if "tsvc_2_5" in root_str:
        bindings_rel = "tsvc_2_5/tsvc_2_5_bindings.py"
    elif "tsvc_2" in root_str:
        bindings_rel = "tsvc_2/tsvc_bindings.py"
    else:
        print(f"  [timing] ERROR: cannot infer TSVC version from root path: {root}", flush=True)
        return None

    bindings_path = pathlib.Path.cwd() / bindings_rel
    if not bindings_path.exists():
        print(f"  [timing] ERROR: bindings file not found: {bindings_path}", flush=True)
        return None

    spec = importlib.util.spec_from_file_location("_tsvc_bindings_tmp", bindings_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
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
# Per-kernel subprocess worker  (mirrors DaCe's _time_one_kernel)
# ---------------------------------------------------------------------------

def _time_one_kernel_worker(args_tuple):
    """
    Runs in an isolated subprocess via Pool.apply_async.
    Times a single kernel symbol from the already-linked .so.
    Returns (sym, base, (median_ns, min_ns, stdev_ns, vec_info, raw_timings)) on success,
    or (sym, None, error_message) on failure.
    """
    so_path_str, sym, base, serial_sig, pool_data, is_float, reps, vec_info = args_tuple

    import ctypes, statistics, numpy as np

    _dp_w   = ctypes.POINTER(ctypes.c_double)
    _fp_w   = ctypes.POINTER(ctypes.c_float)
    _ip_w   = ctypes.POINTER(ctypes.c_int)
    _i64p_w = ctypes.POINTER(ctypes.c_int64)
    _int_w  = ctypes.c_int
    _dbl_w  = ctypes.c_double
    _flt_w  = ctypes.c_float

    _TAG_W = {
        "dp": _dp_w, "fp": _fp_w, "ip": _ip_w, "i64p": _i64p_w,
        "int": _int_w, "dbl": _dbl_w, "flt": _flt_w,
    }

    def _to_carg_w(val, tag):
        ct = _TAG_W[tag]
        if isinstance(val, np.ndarray):
            if ct is _i64p_w:
                return val.astype(np.int64, copy=False).ctypes.data_as(_i64p_w)
            if is_float and val.dtype == np.float64:
                val = val.astype(np.float32)
            elif not is_float and val.dtype == np.float32:
                val = val.astype(np.float64)
            if ct is _ip_w:
                return val.astype("int32", copy=False).ctypes.data_as(_ip_w)
            return val.ctypes.data_as(_fp_w if is_float else _dp_w)
        if ct is _int_w:
            return _int_w(int(val))
        if ct in (_dbl_w, _flt_w):
            return _flt_w(float(val)) if is_float else _dbl_w(float(val))
        return val

    call_args = []
    missing   = []
    for param_name, tag_d, tag_f in serial_sig:
        tag = tag_f if is_float else tag_d
        if param_name not in pool_data:
            missing.append(param_name)
            continue
        call_args.append(_to_carg_w(pool_data[param_name], tag))
    if missing:
        return sym, None, f"unresolved args: {missing}"

    try:
        lib = ctypes.CDLL(so_path_str, ctypes.RTLD_GLOBAL)
    except OSError as exc:
        return sym, None, f"load .so failed: {exc}"

    try:
        fn = getattr(lib, sym)
    except AttributeError:
        return sym, None, f"symbol not found: {sym}"

    fn.restype = None
    timens_buf = np.zeros(1, dtype=np.int64)
    timens_ptr = timens_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_int64))

    try:
        fn(*call_args, timens_ptr)  # warm-up
        timings = []
        for _ in range(reps):
            fn(*call_args, timens_ptr)
            timings.append(int(timens_buf[0]))
    except Exception as exc:
        return sym, None, f"run failed: {exc}"

    med = statistics.median(timings)
    mn  = min(timings)
    sd  = statistics.stdev(timings) if len(timings) > 1 else 0
    # ---- return raw timings alongside aggregates ----
    return sym, base, (med, mn, sd, vec_info, timings)

# ---------------------------------------------------------------------------
# Timing phase — DaCe-style: one kernel per Pool, hard timeout, CSV via write_text
# ---------------------------------------------------------------------------

_DEFAULT_KERNEL_TIMEOUT = 120


def run_timing_phase(
    so_path: pathlib.Path,
    signatures,
    out_csv: pathlib.Path,
    pattern: str,
    reps: int,
    len_1d: int,
    build_dir: Optional[pathlib.Path] = None,
    kernel_timeout: int = _DEFAULT_KERNEL_TIMEOUT,
    debug_kernel: Optional[str] = None,
    raw_csv: Optional[pathlib.Path] = None,  # NEW: path for raw timings CSV
) -> None:
    so_path  = pathlib.Path(so_path)
    out_csv  = pathlib.Path(out_csv)
    is_float = infer_precision_from_pattern(pattern) == "float"
    dtype    = np.float32 if is_float else np.float64
    suffix   = "f" if is_float else "d"
    sym_suffix = f"_{suffix}_single" if "single" in pattern else f"_{suffix}"

    pool_data = _make_array_pool(len_1d, dtype)

    vec_info_map: dict = {}
    if build_dir is not None:
        vec_info_map = parse_vec_reports_detailed(build_dir)

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
        vec_info   = vec_info_map.get(base) or {"vectorized": False, "vec_count": 0, "missed_count": 0}
        work_item  = (str(so_path), sym, base, serial_sig, pool_data, is_float, reps, vec_info)
        result     = _time_one_kernel_worker(work_item)
        sym_r, base_r, payload = result
        if base_r is None:
            print(f"  [debug] FAIL {sym_r} — {payload}", flush=True)
        else:
            med, mn, sd, vi, raw = payload
            print(f"  [debug] ok  {sym_r}  median={med/1e3:.1f}µs  min={mn/1e3:.1f}µs", flush=True)
        return

    # ---- full sweep ----
    rows: list = []
    raw_rows: list = []  # NEW: accumulates (kernel, rep_index, timing_ns) tuples
    n_skipped  = 0

    work_items = []
    for base, sig in sorted(signatures.items()):
        sym        = f"{base}{sym_suffix}"
        serial_sig = _serialise_sig(sig)
        vec_info   = (
            vec_info_map.get(base)
            or vec_info_map.get(sym)
            or {"vectorized": False, "vec_count": 0, "missed_count": 0}
        )
        work_items.append((str(so_path), sym, base, serial_sig, pool_data, is_float, reps, vec_info))

    mp_ctx = multiprocessing.get_context("fork" if sys.platform != "win32" else "spawn")
    mp_pool = mp_ctx.Pool(processes=1)

    try:
        for item in work_items:
            sym  = item[1]
            base = item[2]
            print(f"  [timing] running {sym} ...", end=" ", flush=True)

            async_result = mp_pool.apply_async(_time_one_kernel_worker, (item,))
            try:
                sym_r, base_r, payload = async_result.get(timeout=kernel_timeout)

                if base_r is None:
                    print(f"SKIP — {payload}", flush=True)
                    n_skipped += 1
                else:
                    med, mn, sd, vec_info, timings = payload  # unpack raw timings
                    vec_tag = "VEC" if vec_info["vectorized"] else "---"
                    print(f"ok  median={med/1e3:.1f}µs  min={mn/1e3:.1f}µs  [{vec_tag}]", flush=True)
                    rows.append((sym_r, med, mn, sd, vec_info))
                    # Accumulate raw timings rows
                    for rep_idx, t_ns in enumerate(timings):
                        raw_rows.append((sym_r, rep_idx, t_ns))

            except multiprocessing.TimeoutError:
                print(f"SKIP — timed out after {kernel_timeout}s", flush=True)
                n_skipped += 1
                mp_pool.terminate()
                mp_pool.join()
                mp_pool = mp_ctx.Pool(processes=1)

            except Exception as exc:
                print(f"SKIP — worker error: {exc}", flush=True)
                n_skipped += 1
                mp_pool.terminate()
                mp_pool.join()
                mp_pool = mp_ctx.Pool(processes=1)

    finally:
        mp_pool.terminate()
        mp_pool.join()

    # Write aggregated summary CSV (unchanged format)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    lines = ["kernel,median_ns,min_ns,stdev_ns,vectorized,vec_count,missed_count"]
    for kernel, med, mn, std, vec_info in sorted(rows, key=lambda r: r[0]):
        lines.append(
            f"{kernel},{med:.2f},{mn:.2f},{std:.2f},"
            f"{'1' if vec_info['vectorized'] else '0'},"
            f"{vec_info['vec_count']},"
            f"{vec_info['missed_count']}"
        )
    out_csv.write_text("\n".join(lines) + "\n")

    # Write raw timings CSV
    # Derive raw_csv path from out_csv if not explicitly provided
    if raw_csv is None:
        raw_csv = out_csv.with_name(out_csv.stem + "_raw_timings.csv")
    raw_csv = pathlib.Path(raw_csv)
    raw_csv.parent.mkdir(parents=True, exist_ok=True)
    raw_lines = ["kernel,rep,timing_ns"]
    for kernel, rep_idx, t_ns in raw_rows:
        raw_lines.append(f"{kernel},{rep_idx},{t_ns}")
    raw_csv.write_text("\n".join(raw_lines) + "\n")

    print(
        f"  [timing] {len(rows)} kernels timed, {n_skipped} skipped"
        f" -> {out_csv}",
        flush=True,
    )
    print(f"  [timing] raw timings ({len(raw_rows)} rows) -> {raw_csv}", flush=True)


# ---------------------------------------------------------------------------
# main_compile_cpp
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
    ap.add_argument("root",              nargs="?", default=default_root)
    ap.add_argument("-b", "--build-dir",           default=default_build_dir)
    ap.add_argument("-o", "--so-name",             default=default_so_name)
    ap.add_argument("-f", "--force",  action="store_true")
    ap.add_argument("-j", "--jobs",   type=int,    default=os.cpu_count())
    ap.add_argument("--pattern",                   default="*.cpp")
    ap.add_argument("--vec-report",   action="store_true",
                    help="Capture vectorization remarks into build_dir/*.rpt files.")
    ap.add_argument("--vec-report-out", default=None, metavar="FILE",
                    help="Write vec-report summary text to FILE.")
    ap.add_argument("--time",         action="store_true",
                    help="After linking, time every kernel and write merged CSV.")
    ap.add_argument("--timing-out",   default=None, metavar="FILE",
                    help="Write merged timing+vec CSV to FILE.")
    ap.add_argument("--raw-timing-out", default=None, metavar="FILE",
                    help="Write raw per-repetition timing CSV to FILE. "
                         "Defaults to <timing-out stem>_raw_timings.csv.")  # NEW
    ap.add_argument("--reps",         type=int, default=30, metavar="N")
    ap.add_argument("--len-1d",       type=int, default=1024, metavar="N", dest="len_1d")
    ap.add_argument("--kernel-timeout", type=int, default=_DEFAULT_KERNEL_TIMEOUT,
                    metavar="SEC", dest="kernel_timeout",
                    help="Per-kernel timeout in seconds (default 120). "
                         "Hanging kernels are skipped and the pool is recycled.")
    ap.add_argument("--debug-kernel", default=None, metavar="NAME")

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
        compiled = 0
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
        print(f"Compiled {compiled} objects", flush=True)
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
        vec_detailed = parse_vec_reports_detailed(args.build_dir)
        if vec_detailed:
            vec_count   = sum(1 for v in vec_detailed.values() if v["vectorized"])
            header      = f"Vectorization report {vec_count}/{len(vec_detailed)} kernels vectorized"
            lines       = [header]
            for name, info in sorted(vec_detailed.items()):
                tag = "VEC" if info["vectorized"] else "---"
                lines.append(
                    f"  [{tag}] {name}  "
                    f"(vec={info['vec_count']}, missed={info['missed_count']})"
                )
            report_text = "\n".join(lines)
            print(report_text)

            out_rpt = (
                pathlib.Path(args.vec_report_out) if args.vec_report_out
                else build_dir / f"{pathlib.Path(args.so_name).stem}.vec_report.txt"
            )
            out_rpt.parent.mkdir(parents=True, exist_ok=True)
            out_rpt.write_text(report_text)
            print(f"Saved vec report -> {out_rpt}", flush=True)
        else:
            print("vec-report: No .rpt files found — recompile to generate them.", flush=True)

    # ---- timing phase ----
    if args.time:
        timing_out = (
            pathlib.Path(args.timing_out) if args.timing_out
            else build_dir / f"{pathlib.Path(args.so_name).stem}.timing_report.csv"
        )
        raw_timing_out = (
            pathlib.Path(args.raw_timing_out) if args.raw_timing_out
            else None  # run_timing_phase will auto-derive from timing_out
        )
        signatures = _load_signatures(root, so)
        if signatures is None:
            print("  [timing] WARNING: could not locate tsvc_*_bindings.py — "
                  "timing phase skipped.", flush=True)
        else:
            print(
                f"  Running timing phase "
                f"({args.reps} reps, len_1d={args.len_1d}, "
                f"timeout={args.kernel_timeout}s/kernel) ...",
                flush=True,
            )
            run_timing_phase(
                so_path        = so,
                signatures     = signatures,
                out_csv        = timing_out,
                pattern        = args.pattern,
                reps           = args.reps,
                len_1d         = args.len_1d,
                build_dir      = build_dir,
                kernel_timeout = args.kernel_timeout,
                debug_kernel   = args.debug_kernel,
                raw_csv        = raw_timing_out,  # NEW
            )

    print(f"Done in {_time.perf_counter() - t0:.1f}s", flush=True)
    return 0