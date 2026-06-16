"""Compile per-kernel DaCe ``.py`` files into per-kernel SDFG ``.so``.

Each kernel file under ``microkernels_dace/<kernel>/<kernel>_d.py``
exports one ``@dace.program``; we import it, convert to an SDFG, and
compile under an isolated build folder. Multiprocessing is used per
file because DaCe's compile path is CPU-heavy and the GIL-bound work
inside it serializes thread pools poorly.
"""
import argparse
import contextlib
import ctypes
import importlib.util
import os
import pathlib
import re
import statistics
import subprocess
import sys
import traceback
import time as _time
from typing import List, Optional

import numpy as np

# ── ctypes shorthands ──────────────────────────────────────────────────────────
_dp   = ctypes.POINTER(ctypes.c_double)
_fp   = ctypes.POINTER(ctypes.c_float)
_ip   = ctypes.POINTER(ctypes.c_int)
_i64p = ctypes.POINTER(ctypes.c_int64)

# ── Hardcoded bindings paths ───────────────────────────────────────────────────
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

# ── Internal helpers ───────────────────────────────────────────────────────────

def _import_module_from_path(py_file: pathlib.Path):
    """Import a ``.py`` file as a module without polluting ``sys.modules``."""
    spec = importlib.util.spec_from_file_location(py_file.stem, str(py_file))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load spec for {py_file}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _find_dace_program(mod):
    """Return ``(name, program)`` for the kernel exposed by the module."""
    import dace
    candidates = []
    for name in dir(mod):
        if name.startswith("_"):
            continue
        obj = getattr(mod, name)
        if hasattr(obj, "to_sdfg") or isinstance(obj, dace.SDFG):
            candidates.append((name, obj))
    if len(candidates) == 1:
        return candidates[0]
    for cname, cobj in candidates:
        if cname == mod.__name__ or cname == mod.__name__.removesuffix("_d").removesuffix("_f"):
            return (cname, cobj)
    return candidates[0] if candidates else (None, None)


@contextlib.contextmanager
def _suppress_fd():
    """Silence OS-level stdout/stderr (catches CMake / clang output)."""
    devnull = os.open(os.devnull, os.O_WRONLY)
    old_stdout = os.dup(1)
    old_stderr = os.dup(2)
    try:
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        yield
    finally:
        os.dup2(old_stdout, 1)
        os.dup2(old_stderr, 2)
        os.close(old_stdout)
        os.close(old_stderr)
        os.close(devnull)


def _vec_report_for_dace_kernel(kernel_name: str, build_dir: pathlib.Path) -> str:
    try:
        from compiler_config import CXX, COMPILE_FLAGS
    except ImportError:
        CXX = os.environ.get("CXX", "g++")
        COMPILE_FLAGS = ["-O3", "-std=c++17", "-fPIC"]

    try:
        import dace
        dace_include = str(pathlib.Path(dace.__file__).parent / "runtime" / "include")
    except Exception:
        dace_include = None

    cxx_lower = CXX.lower()
    if "clang" in cxx_lower:
        vec_flags = ["-Rpass=loop-vectorize", "-Rpass-missed=loop-vectorize"]
    elif "icpx" in cxx_lower or "icpc" in cxx_lower:
        vec_flags = ["-qopt-report=2", "-qopt-report-phase=vec"]
    else:
        vec_flags = ["-fopt-info-vec-all"]

    kernel_dir = build_dir / kernel_name
    cpps = sorted(kernel_dir.rglob("*.cpp"))
    cpps = [f for f in cpps if "CMakeFiles" not in str(f)]
    if not cpps:
        return ""

    include_flags = [f"-I{dace_include}"] if dace_include else []
    outputs = []
    for cpp in cpps:
        try:
            r = subprocess.run(
                [CXX, "-c"] + list(COMPILE_FLAGS) + include_flags + vec_flags +
                [str(cpp), "-o", os.devnull],
                stderr=subprocess.PIPE,
                text=True,
            )
            if r.stderr:
                outputs.append(r.stderr)
        except Exception:
            pass
    return "\n".join(outputs)


_VEC_RE = re.compile(
    r"optimized: loop vectorized"
    r"|vectorized loop"
    r"|LOOP AUTO-VECTORIZED",
    re.IGNORECASE,
)


def parse_dace_vec_reports(build_dir) -> dict:
    """Parse all ``*.rpt`` files. Returns ``kernel_name -> bool``."""
    build_dir = pathlib.Path(build_dir)
    results = {}
    for rpt in sorted(build_dir.glob("*.rpt")):
        kernel = re.sub(r"_[df](?:_(?:single|double))?$", "", rpt.stem, flags=re.IGNORECASE)
        text = rpt.read_text()
        results[kernel] = results.get(kernel, False) or bool(_VEC_RE.search(text))
    return results

# ── Compile helpers ────────────────────────────────────────────────────────────

def _compile_one_kernel(py_file: pathlib.Path, build_dir: pathlib.Path, force: bool,
                        vec_report: bool = False) -> dict:
    """Compile a single kernel module into ``<build_dir>/<kernel>``."""
    import dace
    from compiler_config import configure_dace
    configure_dace()

    if "CC" not in os.environ:
        os.environ["CC"] = "gcc"
    if "CXX" not in os.environ:
        os.environ["CXX"] = "g++"

    result = {"file": str(py_file), "stem": py_file.stem, "status": "unknown", "error": None}
    try:
        mod = _import_module_from_path(py_file)
        name, prog = _find_dace_program(mod)
        if prog is None:
            result["status"] = "skipped"
            result["error"] = "no @dace.program or SDFG found"
            return result

        sdfg = prog if isinstance(prog, dace.SDFG) else prog.to_sdfg(simplify=False)
        sdfg.name = py_file.stem

        kernel_build_dir = build_dir / sdfg.name
        kernel_build_dir.mkdir(parents=True, exist_ok=True)
        sdfg.build_folder = str(kernel_build_dir)

        so_path = kernel_build_dir / sdfg.name / "build" / f"lib{sdfg.name}.so"
        if not force and so_path.exists():
            result["status"] = "cached"
            return result

        with _suppress_fd():
            sdfg.compile()
        result["status"] = "compiled"

        if vec_report:
            rpt_text = _vec_report_for_dace_kernel(py_file.stem, build_dir)
            rpt_path = build_dir / f"{py_file.stem}.rpt"
            rpt_path.write_text(rpt_text)
    except Exception as e:
        result["status"] = "failed"
        result["error"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    return result


def _compile_worker(args):
    py_file, build_dir, force, vec_report = args
    return _compile_one_kernel(pathlib.Path(py_file), pathlib.Path(build_dir), force, vec_report)


def compile_dace_all(
    root,
    build_dir,
    force: bool = False,
    pattern: str = "*.py",
    jobs: int = 1,
    vec_report: bool = False,
) -> List[dict]:
    """Compile every kernel ``.py`` under ``root``. Returns one result dict per kernel."""
    root = pathlib.Path(root).resolve()
    build_dir = pathlib.Path(build_dir).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)

    py_files = sorted(
        f for f in root.rglob(pattern)
        if f.name != "__init__.py" and not f.name.startswith("_")
    )
    if not py_files:
        print(f"No kernel files found under {root} with pattern '{pattern}'")
        return []

    work_items = [(str(f), str(build_dir), force, vec_report) for f in py_files]
    if jobs > 1:
        from multiprocessing import Pool
        with Pool(processes=jobs) as pool:
            results = pool.map(_compile_worker, work_items)
    else:
        results = [_compile_worker(item) for item in work_items]
    return results

# ── Timing phase ───────────────────────────────────────────────────────────────

def _infer_tsvc_version_from_path(build_dir: pathlib.Path) -> str:
    """Infer tsvc_2 vs tsvc_2_5 from any part of the build_dir path."""
    for part in build_dir.parts:
        if part == "tsvc_2_5":
            return "tsvc_2_5"
        if part == "tsvc_2":
            return "tsvc_2"
    return "tsvc_2"


def _infer_precision_from_pattern(pattern: str) -> str:
    if "_f_single" in pattern or re.search(r"\*_f\.py$", pattern):
        return "float"
    return "double"


def _make_array_pool(len_1d: int, is_float: bool) -> dict:
    """Allocate named arrays covering all SIGNATURES params for both corpora."""
    dtype  = np.float32 if is_float else np.float64
    len_2d = max(4, int(len_1d ** 0.5))
    len_3d = max(4, int(len_1d ** (1/3)))
    rng    = np.random.default_rng(42)
    return {
        "a":         rng.random(len_1d).astype(dtype),
        "b":         rng.random(len_1d).astype(dtype),
        "c":         rng.random(len_1d).astype(dtype),
        "d":         rng.random(len_1d).astype(dtype),
        "e":         rng.random(len_1d).astype(dtype),
        "x":         rng.random(len_1d).astype(dtype),
        "y":         rng.random(len_1d).astype(dtype),
        "z":         rng.random(len_1d).astype(dtype),
        "q":         rng.random(len_1d).astype(dtype),
        "src":       rng.random(len_1d).astype(dtype),
        "dst":       np.zeros(len_1d, dtype=dtype),
        "out":       np.zeros(len_1d, dtype=dtype),
        "threshold_data": rng.random(len_1d).astype(dtype),
        "aa":        rng.random(len_2d * len_2d).astype(dtype),
        "bb":        rng.random(len_2d * len_2d).astype(dtype),
        "cc":        rng.random(len_2d * len_2d).astype(dtype),
        "flat":      rng.random(len_1d * len_2d).astype(dtype),
        "flat_2d_array": rng.random(len_2d * len_2d).astype(dtype),
        "xx":        rng.random(len_1d).astype(dtype),
        "result":    np.zeros(1, dtype=dtype),
        "result_out":np.zeros(1, dtype=dtype),
        "sum_out":   np.zeros(1, dtype=dtype),
        "dot":       np.zeros(1, dtype=dtype),
        "dot_out":   np.zeros(1, dtype=dtype),
        "ip":        rng.integers(0, len_1d, size=len_1d, dtype=np.int32),
        "indx":      rng.integers(0, len_1d, size=len_1d, dtype=np.int32),
        "idx":       rng.integers(0, len_1d, size=len_1d, dtype=np.int64),
        "mask":      rng.integers(0, 2,       size=len_1d, dtype=np.int64),
        "iterations": 1,
        "len_1d":    len_1d,
        "len_2d":    len_2d,
        "len_3d":    len_3d,
        "vlen":      min(8, len_2d),
        "inc":       1,
        "n1":        1,
        "n3":        len_1d - 1,
        "k":         len_1d // 2,
        "M":         len_1d // 4,
        "threshold": 0,
        "j":         0,
        "ssym":      4,
        "m":         4,
        "t":         4,
        "t1":        4,
        "t2":        4,
        "s":         1.0,
        "s1":        1.0,
        "s2":        2.0,
        "scale":     1.0,
    }


def _load_signatures(build_dir: pathlib.Path) -> Optional[dict]:
    """Load SIGNATURES from the hardcoded bindings file matching the build path."""
    tsvc_version  = _infer_tsvc_version_from_path(build_dir)
    bindings_path = _BINDINGS_MAP[tsvc_version]

    if not bindings_path.exists():
        print(f"  [timing] SKIP — bindings not found: {bindings_path}")
        return None

    spec     = importlib.util.spec_from_file_location(f"{tsvc_version}.bindings", bindings_path)
    bindings = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(bindings)
    except Exception as exc:
        print(f"  [timing] SKIP — failed to load {bindings_path}: {exc}")
        return None

    print(f"  [timing] Using SIGNATURES from {bindings_path} ({len(bindings.SIGNATURES)} kernels)")
    return bindings.SIGNATURES


def _find_dylib(kdir: pathlib.Path, stem: str) -> Optional[pathlib.Path]:
    """
    Find the pre-built shared library for a DaCe kernel without triggering
    a recompile.  DaCe places it at:
      <kdir>/build/lib<stem>.dylib   (macOS)
      <kdir>/build/lib<stem>.so      (Linux)
    """
    build = kdir / "build"
    for ext in (".dylib", ".so"):
        p = build / f"lib{stem}{ext}"
        if p.exists():
            return p
    return None


def _array_to_ptr(arr: np.ndarray, ctype_d, is_float: bool):
    """Cast a numpy array to the correct ctypes pointer type."""
    if ctype_d is _i64p:
        return arr.astype(np.int64, copy=False).ctypes.data_as(_i64p)
    if arr.dtype == np.int32:
        return arr.ctypes.data_as(_ip)
    if is_float:
        a = arr.astype(np.float32) if arr.dtype != np.float32 else arr
        return a.ctypes.data_as(_fp)
    a = arr.astype(np.float64) if arr.dtype != np.float64 else arr
    return a.ctypes.data_as(_dp)


def _build_dace_ctypes_args(sig, pool: dict, is_float: bool):
    """
    Build a ctypes arg list for the DaCe __dace_run_<stem> symbol.
    DaCe-generated run functions accept the same array/scalar arguments
    as the original kernel, prepended by a void* state handle.
    Returns (call_args, ) or None if any param is missing.
    Note: the state handle is prepended by the caller.
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
    return call_args


def run_dace_timing_phase(
    build_dir: pathlib.Path,
    out_path: pathlib.Path,
    pattern: str,
    reps: int,
    len_1d: int,
) -> None:
    """
    Walk *build_dir* for compiled DaCe kernel folders, load each pre-built
    shared library directly (no recompile), and time the ``__dace_run_<stem>``
    symbol *reps* times.  Writes ``timing_report.csv`` to *out_path*.

    DaCe kernel folder layout:
      <build_dir>/<stem>/
        build/
          lib<stem>.dylib  (macOS) / lib<stem>.so  (Linux)  <- loaded here
        src/               <- generated C++ (not touched)
        program.sdfgz      <- SDFG definition  (not loaded here)

    DaCe-generated shared libraries export three symbols:
      void* __dace_init_<stem>()                <- allocates state; called once
      void  __program_<stem>(void* state, args...)  <- timed hot loop
      void  __dace_exit_<stem>(void* state)         <- frees state
    """
    SIGNATURES = _load_signatures(build_dir)
    if SIGNATURES is None:
        return

    is_float = _infer_precision_from_pattern(pattern) == "float"
    pool     = _make_array_pool(len_1d, is_float)
    rows     = []
    skipped  = 0

    kernel_dirs = sorted(
        d for d in build_dir.iterdir()
        if d.is_dir() and (d / "program.sdfgz").exists()
    )
    print(f"  [timing] Found {len(kernel_dirs)} compiled DaCe kernel folders")

    for kdir in kernel_dirs:
        stem = kdir.name                                # e.g. "s111_d_single"
        base = re.sub(r"_(d|f)(_single)?$", "", stem)  # e.g. "s111"

        sig = SIGNATURES.get(base)
        if sig is None:
            print(f"  [timing] SKIP {stem} — not in SIGNATURES (base={base!r})")
            skipped += 1
            continue

        dylib = _find_dylib(kdir, stem)
        if dylib is None:
            print(f"  [timing] SKIP {stem} — no .dylib/.so in {kdir / 'build'}")
            skipped += 1
            continue

        try:
            lib = ctypes.CDLL(str(dylib))
        except OSError as exc:
            print(f"  [timing] SKIP {stem} — cannot load {dylib.name}: {exc}")
            skipped += 1
            continue

        # Resolve DaCe init / run / exit symbols.
        # nm shows the linker adds one leading underscore on macOS, so ctypes
        # strips that automatically — look up without the extra underscore:
        #   ___dace_init_<stem>  -> "__dace_init_<stem>"   (init/exit)
        #   ___program_<stem>    -> "__program_<stem>"      (the hot kernel)
        try:
            fn_init = getattr(lib, f"__dace_init_{stem}")
            fn_exit = getattr(lib, f"__dace_exit_{stem}")
        except AttributeError as exc:
            print(f"  [timing] SKIP {stem} — init/exit symbol missing: {exc}")
            skipped += 1
            continue

        # The run function is __program_<stem> (not __dace_run_<stem>)
        fn_run = None
        for sym in [f"__program_{stem}", f"__dace_run_{stem}", stem]:
            try:
                fn_run = getattr(lib, sym)
                break
            except AttributeError:
                continue
        if fn_run is None:
            print(f"  [timing] SKIP {stem} — run symbol not found")
            skipped += 1
            continue

        call_args = _build_dace_ctypes_args(sig, pool, is_float)
        if call_args is None:
            print(f"  [timing] SKIP {stem} — unresolved arg in pool")
            skipped += 1
            continue

        fn_init.restype = ctypes.c_void_p
        fn_run.restype  = None
        fn_exit.restype = None

        try:
            # __dace_init takes no args on this DaCe version (returns state ptr)
            handle     = fn_init()
            handle_arg = ctypes.c_void_p(handle)

            timings = []
            for _ in range(reps):
                t0 = _time.perf_counter_ns()
                fn_run(handle_arg, *call_args)
                timings.append(_time.perf_counter_ns() - t0)

            fn_exit(handle_arg)

            rows.append((
                base,
                statistics.median(timings),
                min(timings),
                statistics.stdev(timings) if reps > 1 else 0.0,
            ))
        except Exception as exc:
            print(f"  [timing] SKIP {stem} — call failed: {exc}")
            skipped += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["kernel,median_ns,min_ns,stdev_ns"]
    for kernel, med, mn, std in sorted(rows):
        lines.append(f"{kernel},{med:.0f},{mn:.0f},{std:.0f}")
    out_path.write_text("\n".join(lines) + "\n")
    print(f"  [timing] {len(rows)} kernels timed, {skipped} skipped -> {out_path}")

# ── main_compile_dace ──────────────────────────────────────────────────────────

def main_compile_dace(default_root: str, default_build_dir: str, argv: "list | None" = None) -> int:
    """Argparse wrapper used by ``tsvc_2/`` and ``tsvc_2_5/`` entry points."""
    ap = argparse.ArgumentParser(description="Compile per-kernel DaCe .py SDFGs in parallel.")
    ap.add_argument("root",          nargs="?", default=default_root)
    ap.add_argument("-b", "--build-dir",        default=default_build_dir)
    ap.add_argument("-f", "--force",            action="store_true")
    ap.add_argument("-j", "--jobs",             type=int, default=os.cpu_count())
    ap.add_argument("--pattern",               default="*.py")
    ap.add_argument("--vec-report",            action="store_true",
                    help="Recompile DaCe-generated C++ with vec remarks into <build_dir>/<kernel>.rpt files.")
    ap.add_argument("--vec-report-out",        default=None, metavar="FILE",
                    help="Write vec summary to FILE (default: <build_dir>/dace.vec_report.txt).")
    ap.add_argument("--time",                  action="store_true",
                    help="After compiling, load each kernel SDFG and time it.")
    ap.add_argument("--timing-out",            default=None, metavar="FILE",
                    help="Write timing CSV to FILE (default: <build_dir>/dace.timing_report.csv).")
    ap.add_argument("--reps",                  type=int, default=30, metavar="N",
                    help="Timing repetitions per kernel (default: 30).")
    ap.add_argument("--len-1d",                type=int, default=1024, metavar="N",
                    dest="len_1d",
                    help="Array length used during timing (default: 1024).")
    args = ap.parse_args(argv)

    root     = pathlib.Path(args.root).resolve()
    py_files = sorted(
        f for f in root.rglob(args.pattern)
        if f.name != "__init__.py" and not f.name.startswith("_")
    )
    print(f"Found {len(py_files)} DaCe kernel files under {root}")

    t0      = _time.perf_counter()
    results = compile_dace_all(
        root=args.root,
        build_dir=args.build_dir,
        force=args.force,
        pattern=args.pattern,
        jobs=args.jobs,
        vec_report=args.vec_report,
    )
    dt = _time.perf_counter() - t0

    compiled = sum(1 for r in results if r["status"] == "compiled")
    cached   = sum(1 for r in results if r["status"] == "cached")
    skipped  = sum(1 for r in results if r["status"] == "skipped")
    failed   = sum(1 for r in results if r["status"] == "failed")
    for r in results:
        if r["status"] == "failed":
            print(f"  FAIL: {r['stem']}: {r['error']}")
        elif r["status"] == "skipped":
            print(f"  SKIP: {r['stem']}: {r['error']}")
    if failed or skipped:
        print(f"\n{compiled} compiled, {cached} cached, {skipped} skipped, {failed} failed")

    # ── Vectorization report ──────────────────────────────────────────────────
    if args.vec_report:
        vec_results = parse_dace_vec_reports(args.build_dir)
        vec_count   = sum(1 for v in vec_results.values() if v)
        header      = f"DaCe vectorization report: {vec_count}/{len(vec_results)} kernels vectorized"
        lines       = [header]
        for name, vec in sorted(vec_results.items()):
            lines.append(f"  {'VEC' if vec else '---'}  {name}")

        report_text = "\n".join(lines) + "\n"
        print(report_text, end="")

        out_path = pathlib.Path(args.vec_report_out) if args.vec_report_out \
                    else pathlib.Path(args.build_dir) / "dace.vec_report.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_text)
        print(f"Saved vec report  -> {out_path}")

    # ── Timing report ─────────────────────────────────────────────────────────
    if args.time:
        timing_out = pathlib.Path(args.timing_out) if args.timing_out \
                      else pathlib.Path(args.build_dir) / "dace.timing_report.csv"

        print(f"Running DaCe timing phase ({args.reps} reps, len_1d={args.len_1d}) ...")
        run_dace_timing_phase(
            build_dir = pathlib.Path(args.build_dir).resolve(),
            out_path  = timing_out,
            pattern   = args.pattern,
            reps      = args.reps,
            len_1d    = args.len_1d,
        )

    print(f"Done in {dt:.1f}s")
    return 0