"""Compile per-kernel ``.cpp`` files into a single shared library.

Walks a ``microkernels_cpp/`` root for ``*.cpp`` files, compiles each
to ``.o`` with header-aware dependency tracking, then links them all
into one ``.so``. Shared by tsvc_2 and tsvc_2_5.
"""
import argparse
import ctypes
import os
import pathlib
import re
import statistics
import subprocess
from typing import List, Optional

import numpy as np

from compiler_config import CXX, COMPILE_FLAGS, LINK_FLAGS  # repo-root shim


# ── ctypes shorthands ──────────────────────────────────────────────────────────
_dp   = ctypes.POINTER(ctypes.c_double)
_fp   = ctypes.POINTER(ctypes.c_float)
_ip   = ctypes.POINTER(ctypes.c_int)
_i64p = ctypes.POINTER(ctypes.c_int64)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _obj_path(src: pathlib.Path, build_dir: pathlib.Path) -> pathlib.Path:
    return build_dir / f"{src.stem}.o"


def _dep_path(obj: pathlib.Path) -> pathlib.Path:
    return obj.with_suffix(".d")


def _parse_depfile(dep: pathlib.Path) -> List[pathlib.Path]:
    """Parse a GCC/Clang ``.d`` Makefile-style dependency file."""
    if not dep.exists():
        return []
    _, _, rhs = dep.read_text().partition(":")
    rhs = rhs.replace("\\\n", " ")
    return [pathlib.Path(p) for p in rhs.split() if p]


def _needs_rebuild(src: pathlib.Path, obj: pathlib.Path) -> bool:
    if not obj.exists():
        return True
    obj_mtime = obj.stat().st_mtime
    deps = _parse_depfile(_dep_path(obj))
    if deps:
        for dep in deps:
            try:
                if dep.stat().st_mtime > obj_mtime:
                    return True
            except FileNotFoundError:
                return True
        return False
    return src.stat().st_mtime > obj_mtime


def _vec_report_flag() -> List[str]:
    """Return compiler flag(s) that emit vectorization remarks to stderr."""
    cxx_lower = CXX.lower()
    if "clang" in cxx_lower:
        return ["-Rpass=loop-vectorize", "-Rpass-missed=loop-vectorize"]
    if "icpx" in cxx_lower or "icpc" in cxx_lower:
        return ["-qopt-report=2", "-qopt-report-phase=vec"]
    return ["-fopt-info-vec-all"]


# ── Compile / link ─────────────────────────────────────────────────────────────

def compile_object(src,
                   build_dir,
                   extra_flags: Optional[List[str]] = None,
                   force: bool = False,
                   vec_report: bool = False) -> pathlib.Path:
    """Compile a single ``.cpp`` to its ``.o``."""
    src = pathlib.Path(src).resolve()
    build_dir = pathlib.Path(build_dir).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    obj = _obj_path(src, build_dir)
    if not force and not _needs_rebuild(src, obj):
        return obj
    flags = list(COMPILE_FLAGS)
    if extra_flags:
        flags.extend(extra_flags)
    if vec_report:
        flags.extend(_vec_report_flag())
    rpt_path = obj.with_suffix(".rpt")
    result = subprocess.run(
        [CXX, "-c"] + flags + [str(src), "-o", str(obj)],
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, result.args, stderr=result.stderr)
    if vec_report:
        rpt_path.write_text(result.stderr)
    return obj


def parse_vec_reports(build_dir) -> dict:
    """Parse all ``*.rpt`` files and return kernel_name -> bool (vectorized)."""
    build_dir = pathlib.Path(build_dir)
    vec_re = re.compile(
        r"optimized: loop vectorized"
        r"|vectorized loop"
        r"|LOOP AUTO-VECTORIZED",
        re.IGNORECASE,
    )
    results = {}
    for rpt in sorted(build_dir.glob("*.rpt")):
        kernel = re.sub(r"_(d|f)(_single)?$", "", rpt.stem)
        text = rpt.read_text()
        results[kernel] = results.get(kernel, False) or bool(vec_re.search(text))
    return results


def link_library(
    objects: List[pathlib.Path],
    build_dir,
    so_name: str,
    extra_link_flags: Optional[List[str]] = None,
) -> pathlib.Path:
    build_dir = pathlib.Path(build_dir).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    so = build_dir / so_name
    flags = list(LINK_FLAGS)
    if extra_link_flags:
        flags.extend(extra_link_flags)
    subprocess.check_call([CXX] + flags + [str(o) for o in objects] + ["-o", str(so)])
    return so


def compile_cpp_library(
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
            futs = {pool.submit(compile_object, cpp, build_dir, extra_flags, force, vec_report): cpp for cpp in cpps}
            for fut in as_completed(futs):
                cpp = futs[fut]
                try:
                    objects.append(fut.result())
                except subprocess.CalledProcessError as e:
                    print(f"FAIL: {cpp.name}: {e}")
    else:
        objects = [compile_object(cpp, build_dir, extra_flags, force, vec_report) for cpp in cpps]

    return link_library(objects, build_dir, so_name, extra_link_flags)


def load_cpp_library(root, build_dir, so_name: str, **kwargs) -> ctypes.CDLL:
    so = compile_cpp_library(root, build_dir, so_name, **kwargs)
    return ctypes.CDLL(str(so))


# ── Timing phase ───────────────────────────────────────────────────────────────

def _infer_precision_from_pattern(pattern: str) -> str:
    """Guess double/float from the glob pattern used during compile."""
    if "_f_single" in pattern or pattern.endswith("_f.cpp"):
        return "float"
    return "double"


def _make_array_pool(len_1d: int, is_float: bool) -> dict:
    """Allocate a pool of named arrays that cover every SIGNATURES entry."""
    dtype  = np.float32 if is_float else np.float64
    len_2d = max(4, int(len_1d ** 0.5))
    rng    = np.random.default_rng(42)
    return {
        # 1-D arrays
        "a":         rng.random(len_1d).astype(dtype),
        "b":         rng.random(len_1d).astype(dtype),
        "c":         rng.random(len_1d).astype(dtype),
        "d":         rng.random(len_1d).astype(dtype),
        "e":         rng.random(len_1d).astype(dtype),
        "x":         rng.random(len_1d).astype(dtype),
        "q":         rng.random(len_1d).astype(dtype),
        # 2-D arrays (flattened)
        "aa":        rng.random(len_2d * len_2d).astype(dtype),
        "bb":        rng.random(len_2d * len_2d).astype(dtype),
        "cc":        rng.random(len_2d * len_2d).astype(dtype),
        "flat":      rng.random(len_1d * len_2d).astype(dtype),
        "flat_2d_array": rng.random(len_1d * len_2d).astype(dtype),
        # Reduction outputs
        "result":    np.zeros(1, dtype=dtype),
        "result_out":np.zeros(1, dtype=dtype),
        "sum_out":   np.zeros(1, dtype=dtype),
        "dot":       np.zeros(1, dtype=dtype),
        "dot_out":   np.zeros(1, dtype=dtype),
        # Integer arrays (int32)
        "ip":        rng.integers(0, len_1d, size=len_1d, dtype=np.int32),
        "indx":      rng.integers(0, len_1d, size=len_1d, dtype=np.int32),
        # Int64 arrays — tsvc_2_5 uses these for idx / mask / ip params
        "idx":       rng.integers(0, len_1d, size=len_1d, dtype=np.int64),
        "mask":      rng.integers(0, 2,       size=len_1d, dtype=np.int64),
        # Scalars
        "iterations": 1,
        "len_1d":    len_1d,
        "len_2d":    len_2d,
        "vlen":      min(8, len_2d),
        "inc":       1,
        "n1":        1,
        "n3":        len_1d - 1,
        "k":         len_1d // 2,
        "M":         len_1d // 4,
        "threshold": 0,
        "j":         0,
        "s":         1.0,
        "s1":        1.0,
        "s2":        2.0,
        # tsvc_2_5 scalar params
        "ssym":      4,
        "m":         4,
        "t":         4,
        "t1":        4,
        "t2":        4,
        "len_2d":    len_2d,
        "len_3d":    max(4, int(len_1d ** (1/3))),
        "scale":     1.0,
        "threshold_data": rng.random(len_1d).astype(dtype),
        "out":       np.zeros(len_1d, dtype=dtype),
        "x":         rng.random(len_1d).astype(dtype),
        "y":         rng.random(len_1d).astype(dtype),
        "z":         rng.random(len_1d).astype(dtype),
        "src":       rng.random(len_1d).astype(dtype),
        "dst":       np.zeros(len_1d, dtype=dtype),
    }


def _array_to_ptr(arr: np.ndarray, ctype_d, is_float: bool):
    """Return the correct ctypes pointer for a numpy array.

    Handles three cases:
    - int64 arrays (_i64p) used by tsvc_2_5 for idx/mask/ip params
    - int32 arrays (_ip)
    - float32/float64 arrays
    """
    if ctype_d is _i64p:
        return arr.astype(np.int64, copy=False).ctypes.data_as(_i64p)
    if arr.dtype == np.int32:
        return arr.ctypes.data_as(_ip)
    if is_float:
        a = arr.astype(np.float32) if arr.dtype != np.float32 else arr
        return a.ctypes.data_as(_fp)
    a = arr.astype(np.float64) if arr.dtype != np.float64 else arr
    return a.ctypes.data_as(_dp)


def _resolve_call_args(sig, pool: dict, is_float: bool):
    """
    Build a ctypes argument list for one kernel from the pool.
    Returns (call_args, time_buf) or None if a param is unknown.
    """
    call_args = []
    for pname, ctype_d, ctype_f in sig:
        val = pool.get(pname)
        if val is None:
            return None
        if isinstance(val, np.ndarray):
            call_args.append(_array_to_ptr(val, ctype_d, is_float))
        elif isinstance(val, float):
            call_args.append(ctypes.c_float(val) if is_float else ctypes.c_double(val))
        else:
            call_args.append(ctypes.c_int(int(val)))

    time_buf = (ctypes.c_int64 * 1)(0)
    call_args.append(time_buf)
    return call_args, time_buf


def run_timing_phase(
    so_path: pathlib.Path,
    out_path: pathlib.Path,
    pattern: str,
    reps: int,
    len_1d: int,
) -> None:
    """
    Load *so_path*, iterate over every kernel whose symbol matches the
    compiled pattern, call it *reps* times, and write timing_report.csv
    to *out_path*.

    The function resolves the SIGNATURES table automatically from the
    tsvc_bindings module sitting alongside compile_cpp_kernels.py.
    """
    # ── Resolve SIGNATURES ────────────────────────────────────────────────────
    # Hardcoded absolute paths to both bindings files.
    import importlib.util

    _BINDINGS_MAP = {
        "tsvc_2": pathlib.Path(
            "/Users/alexbonsall/Desktop/ETH/Semester_Thesis/VectraArtifacts"
            "/tsvc_2/tsvc_bindings.py"
        ),
        "tsvc_2_5": pathlib.Path(
            "/Users/alexbonsall/Desktop/ETH/Semester_Thesis/VectraArtifacts"
            "/tsvc_2_5/tsvc_2_5_bindings.py"
        ),
    }

    # Infer which bindings to use from the so_path location.
    # so_path will contain "tsvc_2_5" or "tsvc_2" somewhere in its parts.
    _tsvc_version = "tsvc_2"   # default
    for _part in so_path.parts:
        if _part == "tsvc_2_5":
            _tsvc_version = "tsvc_2_5"
            break
        if _part == "tsvc_2":
            _tsvc_version = "tsvc_2"
            break

    _bindings_path = _BINDINGS_MAP[_tsvc_version]
    if not _bindings_path.exists():
        print(f"  [timing] SKIP — bindings file not found: {_bindings_path}")
        return

    _spec = importlib.util.spec_from_file_location(
        f"{_tsvc_version}.bindings", _bindings_path
    )
    _bindings = importlib.util.module_from_spec(_spec)
    try:
        _spec.loader.exec_module(_bindings)
        SIGNATURES = _bindings.SIGNATURES
    except Exception as exc:
        print(f"  [timing] SKIP — failed to load {_bindings_path}: {exc}")
        return

    print(f"  [timing] Using SIGNATURES from {_bindings_path} ({len(SIGNATURES)} kernels)")

    is_float = _infer_precision_from_pattern(pattern)  == "float"

    # Symbol suffix: _d_single / _f_single (tsvc_2) or _d / _f (tsvc_2_5)
    if "_single" in pattern:
        sym_suffix = "_f_single" if is_float else "_d_single"
    else:
        sym_suffix = "_f" if is_float else "_d"

    pool = _make_array_pool(len_1d, is_float)

    try:
        lib = ctypes.CDLL(str(so_path))
    except OSError as exc:
        print(f"  [timing] SKIP — cannot load {so_path}: {exc}")
        return

    rows    = []
    skipped = 0

    for base, sig in SIGNATURES.items():
        sym = f"{base}{sym_suffix}"
        try:
            fn = getattr(lib, sym)
        except AttributeError:
            skipped += 1
            continue

        resolved = _resolve_call_args(sig, pool, is_float)
        if resolved is None:
            skipped += 1
            continue
        call_args, time_buf = resolved
        fn.restype = None

        try:
            timings = []
            for _ in range(reps):
                fn(*call_args)
                timings.append(time_buf[0])

            rows.append((
                base,
                statistics.median(timings),
                min(timings),
                statistics.stdev(timings) if reps > 1 else 0.0,
            ))
        except Exception as exc:
            skipped += 1
            continue

    # ── Write CSV ─────────────────────────────────────────────────────────────
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["kernel,median_ns,min_ns,stdev_ns"]
    for kernel, med, mn, std in sorted(rows):
        lines.append(f"{kernel},{med:.0f},{mn:.0f},{std:.0f}")
    out_path.write_text("\n".join(lines) + "\n")

    print(f"  [timing] {len(rows)} kernels timed, {skipped} skipped -> {out_path}")


# ── main_compile_cpp ───────────────────────────────────────────────────────────

def main_compile_cpp(default_root: str,
                     default_build_dir: str,
                     default_so_name: str,
                     argv: "list | None" = None) -> int:
    """Argparse wrapper used by ``tsvc_2/`` and ``tsvc_2_5/`` entry points."""
    import time as _time
    ap = argparse.ArgumentParser(description="Compile per-kernel .cpp into a single shared library.")
    ap.add_argument("root", nargs="?", default=default_root,
                    help="Root directory of kernel sources.")
    ap.add_argument("-b", "--build-dir", default=default_build_dir)
    ap.add_argument("-o", "--so-name",   default=default_so_name)
    ap.add_argument("-f", "--force",     action="store_true")
    ap.add_argument("-j", "--jobs",      type=int, default=os.cpu_count())
    ap.add_argument("--pattern",         default="*.cpp")
    ap.add_argument("--vec-report",      action="store_true",
                    help="Capture vectorization remarks into <build_dir>/*.rpt files.")
    ap.add_argument("--vec-report-out",  default=None, metavar="FILE",
                    help="Write the vec summary to FILE "
                         "(default: <so_name>.vec_report.txt when --vec-report is set).")
    # ── timing flags ──────────────────────────────────────────────────────────
    ap.add_argument("--time",            action="store_true",
                    help="After linking, load the .so and time every kernel.")
    ap.add_argument("--timing-out",      default=None, metavar="FILE",
                    help="Write timing CSV to FILE "
                         "(default: <build_dir>/<so_stem>.timing_report.csv).")
    ap.add_argument("--reps",            type=int, default=30, metavar="N",
                    help="Timing repetitions per kernel (default: 30).")
    ap.add_argument("--len-1d",          type=int, default=1024, metavar="N",
                    dest="len_1d",
                    help="Array length used during timing (default: 1024).")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.root).resolve()
    cpps = sorted(root.rglob(args.pattern))
    print(f"Found {len(cpps)} source files under {root}")

    t0 = _time.perf_counter()

    if args.jobs > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        objects: List[pathlib.Path] = []
        compiled = cached = 0
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futs = {
                pool.submit(compile_object, cpp, args.build_dir,
                            force=args.force, vec_report=args.vec_report): cpp
                for cpp in cpps
            }
            for fut in as_completed(futs):
                cpp = futs[fut]
                try:
                    obj = fut.result()
                    objects.append(obj)
                    compiled += 1
                except subprocess.CalledProcessError as e:
                    print(f"FAIL: {cpp.name}: {e}")
                    compiled += 1
        print(f"Compile: {compiled} files processed")
    else:
        objects = [
            compile_object(cpp, args.build_dir,
                           force=args.force, vec_report=args.vec_report)
            for cpp in cpps
        ]

    so = link_library(objects, args.build_dir, args.so_name)
    print(f"Linked {len(objects)} objects -> {so}")

    # ── Vectorization report ──────────────────────────────────────────────────
    if args.vec_report:
        results   = parse_vec_reports(args.build_dir)
        vec_count = sum(1 for v in results.values() if v)
        header    = f"Vectorization report: {vec_count}/{len(results)} kernels vectorized"
        lines     = [header]
        for name, vec in sorted(results.items()):
            status = "VEC" if vec else "---"
            lines.append(f"  {status}  {name}")

        report_text = "\n".join(lines) + "\n"
        print(report_text, end="")

        out_path = args.vec_report_out
        if out_path is None:
            so_stem  = pathlib.Path(args.so_name).stem
            out_path = pathlib.Path(args.build_dir) / f"{so_stem}.vec_report.txt"
        else:
            out_path = pathlib.Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_text)
        print(f"Saved vec report  -> {out_path}")

    # ── Timing report ─────────────────────────────────────────────────────────
    if args.time:
        timing_out = args.timing_out
        if timing_out is None:
            so_stem    = pathlib.Path(args.so_name).stem
            timing_out = pathlib.Path(args.build_dir) / f"{so_stem}.timing_report.csv"
        else:
            timing_out = pathlib.Path(timing_out)

        print(f"Running timing phase ({args.reps} reps, len_1d={args.len_1d}) ...")
        run_timing_phase(
            so_path  = so,
            out_path = timing_out,
            pattern  = args.pattern,
            reps     = args.reps,
            len_1d   = args.len_1d,
        )

    print(f"Done in {_time.perf_counter() - t0:.1f}s")
    return 0