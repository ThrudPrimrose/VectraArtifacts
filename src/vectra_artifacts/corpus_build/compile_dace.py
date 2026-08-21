#!/usr/bin/env python3
"""compile_dace.py — compile and time DaCe TSVC-2 kernels.

Vectorization ground truth
---------------------------
Compiler remarks (GCC -fopt-info-vec-*, Clang -Rpass=loop-vectorize) can be
misleading: a compiler may emit an "optimized: loop vectorized" remark for a
transform that a *later* legality/cost-model pass invalidates, leaving pure
scalar code in the final object. This was observed empirically (TSVC kernels
s231, s2102, s1232, ...) where the remark said "vectorized" but the emitted
machine code contained zero SIMD instructions.

To avoid trusting the remark text, this script now compiles each kernel with
-S to a real assembly file and scans it directly for SIMD register/opcode
usage (AArch64 NEON/SVE, x86 AVX/AVX-512). That scan is the authoritative
`vectorized` verdict. The remark-derived verdict is still parsed and kept
alongside it (`remark_vectorized`) purely as a diagnostic — a mismatch
between the two is flagged explicitly so these false "optimized" claims are
caught automatically instead of requiring manual disassembly review.
"""

from __future__ import annotations

import argparse
import fnmatch
import multiprocessing
import os
import pathlib
import re
import subprocess
import sys
import time as _time
from typing import Optional


import numpy as np

from vectra_artifacts.compilers import flags as _flags


# ── Vectorization remark patterns (diagnostic only — NOT ground truth) ────────
_VEC_OPTIMIZED_RE = re.compile(
    r"remark.*vectorized loop"
    r"|note.*loop vectorized"
    r"|optimized.*loop vectorized"
    r"|note.*vectorized (?!0\b)\d+ loop"
    r"|LOOP AUTO-VECTORIZED"
    r"|loop vectorized"
    r"|LOOP VECTORIZED",
    re.IGNORECASE,
)
_VEC_MISSED_RE = re.compile(
    r"(remark.*loop not vectorized"
    r"|note.*not vectorized"
    r"|missed.*loop"
    r"|couldn.t vectorize"
    r"|not vectorized"
    r"|missed.*vectoriz)",
    re.IGNORECASE,
)


def _parse_vec_from_text(text: str) -> dict:
    """Diagnostic-only parse of compiler remark text. Do NOT treat the
    'vectorized' field from this function as ground truth — see module
    docstring. Use `_parse_vec_from_asm` / `_vec_info_for_kernel` instead."""
    vec_lines    = [l.strip() for l in text.splitlines() if _VEC_OPTIMIZED_RE.search(l)]
    missed_lines = [l.strip() for l in text.splitlines() if _VEC_MISSED_RE.search(l)]
    return {
        "vectorized":     len(vec_lines) > 0,
        "vec_count":      len(vec_lines),
        "missed_count":   len(missed_lines),
        "sample_remarks": (vec_lines + missed_lines)[:5],
    }


# ── Assembly-based ground-truth vectorization detection ───────────────────────
# Shared with compile_cpp.py via vec_ground_truth.py — see that module's
# docstring for the function-label-matching bug this used to carry as two
# separately-drifting copies (a real function's vectorized body could be
# silently dropped from the scan entirely, producing a false "not
# vectorized" verdict and a spurious remark_mismatch).
from .vec_ground_truth import parse_vec_from_asm as _parse_vec_from_asm


# ── Remark flags per compiler ──────────────────────────────────────────────────
# Sourced from vectra_artifacts.compilers.flags's canonical, all-pass remark
# table (not a narrower loop-vectorize-only copy) so kernels vectorized by a
# different pass (e.g. Clang's separate SLP vectorizer) don't silently read
# back as unvectorized here just because this diagnostic recompile asked for
# fewer remarks than the real build actually got.
def _remark_flags_for(executable: str) -> list[str]:
    base = pathlib.Path(executable).name.lower()
    if "icpx" in base:
        compiler = _flags.Compiler.ICPX
    elif "clang" in base:
        compiler = _flags.Compiler.CLANG
    elif "g++" in base or "gcc" in base:
        compiler = _flags.Compiler.GCC
    else:
        return []
    return list(_flags.get_remark_flags(compiler))


def _remark_flags_str_for(executable: str) -> str:
    return " ".join(_remark_flags_for(executable))


# ── Output file paths for a kernel dir ────────────────────────────────────────
def _rpt_path(kdir: pathlib.Path) -> pathlib.Path:
    return kdir / "vec_remarks.rpt"


def _asm_path(kdir: pathlib.Path) -> pathlib.Path:
    """Real compiler-emitted assembly (-S output), used for ground-truth
    vectorization detection. Distinct from any objdump-of-.o disassembly
    that a separate sweep script may also produce."""
    return kdir / "vec_check.s"


# ── Parse flags.make ──────────────────────────────────────────────────────────
def _parse_flags_make(flags_make: pathlib.Path) -> tuple[str, list[str], list[str], list[str]]:
    """Return (compiler_exe, cxx_flags, cxx_defines, cxx_includes).
    Handles Apple Silicon's CXX_FLAGSarm64 key."""
    compiler_exe = ""
    cxx_flags: list[str] = []
    cxx_defines: list[str] = []
    cxx_includes: list[str] = []

    text = flags_make.read_text(errors="ignore")

    for line in text.splitlines():
        m = re.match(r"#\s*compile\s+CXX\s+with\s+(\S+)", line)
        if m:
            compiler_exe = m.group(1)
            break

    for line in text.splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        key, _, val = line.partition("=")
        key = key.strip(); val = val.strip()
        if re.match(r"CXX_FLAGS", key):
            cxx_flags = val.split()
        elif key == "CXX_DEFINES":
            cxx_defines = val.split()
        elif key == "CXX_INCLUDES":
            cxx_includes = val.split()

    return compiler_exe, cxx_flags, cxx_defines, cxx_includes


# ── Re-run compiler to produce .rpt + real assembly (-S) ──────────────────────
def _generate_rpt_for_kernel(
    kdir: pathlib.Path,
    extra_flags: "list[str] | None" = None,
) -> "pathlib.Path | None":
    """Recompile the kernel's .cpp with -S, keeping BOTH the remark text
    (.rpt) and the actual emitted assembly (vec_check.s). The assembly is
    what `_vec_info_for_kernel` treats as ground truth."""
    rpt = _rpt_path(kdir)
    asm_out = _asm_path(kdir)
    build_root = kdir / "build"
    if not build_root.is_dir():
        return None

    src_cpp: Optional[pathlib.Path] = None
    for c in sorted(build_root.rglob("src/cpu/*.cpp"), key=lambda p: len(p.parts), reverse=True):
        src_cpp = c
        break
    if src_cpp is None:
        for c in build_root.rglob("*.cpp"):
            if "CMakeFiles" in str(c) or "/sample/" in str(c):
                continue
            src_cpp = c
            break
    if src_cpp is None:
        return None

    flags_make: Optional[pathlib.Path] = None
    candidates = [f for f in build_root.rglob("flags.make")
                  if "dacestub" not in f.parts[-2]]
    if candidates:
        flags_make = max(candidates, key=lambda p: len(p.parts))
    elif list(build_root.rglob("flags.make")):
        flags_make = max(build_root.rglob("flags.make"), key=lambda p: len(p.parts))

    if flags_make is None:
        return None

    compiler_exe, cxx_flags, cxx_defines, cxx_includes = _parse_flags_make(flags_make)
    if not compiler_exe:
        compiler_exe = os.environ.get("DACE_compiler_cpu_executable", "g++")

    remark_flags = _remark_flags_for(compiler_exe)
    if not remark_flags:
        return None

    cmd = (
        [compiler_exe]
        + cxx_defines
        + cxx_includes
        + cxx_flags
        + (extra_flags or [])
        + remark_flags
        + ["-S", "-o", str(asm_out), str(src_cpp.resolve())]
    )

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(flags_make.parent.parent.resolve()),
        )
        output = result.stderr + result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        output = ""

    rpt.write_text(output)
    return rpt


def _vec_info_for_kernel(kdir: pathlib.Path) -> dict:
    """
    Authoritative vectorization info for a compiled kernel folder.

    `vectorized` / `vec_count` come from scanning the real compiled assembly
    (ground truth). `remark_vectorized` is what the compiler's text remarks
    claimed, kept purely for comparison. `remark_mismatch` is True whenever
    the two disagree — i.e. exactly the "report said vectorized but the
    binary is scalar" situation found manually in kernels like s231, s2102,
    s1232 during earlier analysis.
    """
    asm_path = _asm_path(kdir)
    rpt = _rpt_path(kdir)

    remark_info = (
        _parse_vec_from_text(rpt.read_text(errors="ignore"))
        if rpt.exists() else _parse_vec_from_text("")
    )

    if asm_path.exists():
        asm_info = _parse_vec_from_asm(asm_path.read_text(errors="ignore"))
    else:
        asm_info = {
            "vectorized": False, "vec_count": 0, "missed_count": 0,
            "sample_remarks": [], "source": "unavailable",
        }

    return {
        "vectorized":        asm_info["vectorized"],       # ground truth
        "vec_count":         asm_info["vec_count"],
        "missed_count":      remark_info["missed_count"],  # only remarks explain *why* something missed
        "sample_remarks":    asm_info["sample_remarks"] or remark_info["sample_remarks"],
        "remark_vectorized": remark_info["vectorized"],
        "remark_mismatch":   asm_info["vectorized"] != remark_info["vectorized"],
        "source":            asm_info["source"],
    }


def _vec_info_from_rpt(kdir: pathlib.Path) -> dict:
    """Deprecated: remark-text-only parse, kept for backward compatibility.
    Prefer `_vec_info_for_kernel`, which checks the actual assembly."""
    rpt = _rpt_path(kdir)
    if rpt.exists():
        return _parse_vec_from_text(rpt.read_text(errors="ignore"))
    return _parse_vec_from_text("")


# ── Extra flags from environment ───────────────────────────────────────────────
def _extra_flags_from_env() -> list[str]:
    return os.environ.get("CXXFLAGS", "").split()


# ── Array pool ─────────────────────────────────────────────────────────────────
def _make_array_pool(len_1d: int, is_float: bool) -> dict:
    dtype  = np.float32 if is_float else np.float64
    rng    = np.random.default_rng(42)
    SSYM   = 4
    S_TILE = 32
    T_TILE = 32

    dim_2d  = min(len_1d, 4096)
    arr_2d  = rng.random((dim_2d, dim_2d)).astype(dtype)
    dim_3d  = 32
    arr_3d  = rng.random((dim_3d, dim_3d, dim_3d)).astype(dtype)
    idx_arr = np.mod(np.arange(len_1d, dtype=np.int64) * 7 + 3, len_1d)

    return {
        "a": arr_2d.ravel().copy(), "b": arr_2d.ravel().copy(),
        "c": rng.random(len_1d).astype(dtype),
        "d": rng.random(len_1d).astype(dtype),
        "e": rng.random(len_1d).astype(dtype),
        "f": rng.random(len_1d).astype(dtype),
        "g": rng.random(len_1d).astype(dtype),
        "h": rng.random(len_1d).astype(dtype),
        "u": rng.random(len_1d).astype(dtype),
        "v": rng.random(len_1d).astype(dtype),
        "w": rng.random(len_1d).astype(dtype),
        "x": rng.random(len_1d).astype(dtype),
        "y": rng.random(len_1d).astype(dtype),
        "z": rng.random(len_1d).astype(dtype),
        "d_": rng.random(len_1d).astype(dtype),
        "aa": rng.random(dim_2d * dim_2d).astype(dtype),
        "bb": rng.random(dim_2d * dim_2d).astype(dtype),
        "cc": rng.random(dim_2d * dim_2d).astype(dtype),
        "dd": rng.random(dim_2d * dim_2d).astype(dtype),
        "xx": rng.random(len_1d).astype(dtype),
        "p": rng.random(len_1d).astype(dtype),
        "q": rng.random(len_1d).astype(dtype),
        "r": rng.random(len_1d).astype(dtype),
        "in_": rng.random(len_1d).astype(dtype),
        "src": rng.random(len_1d).astype(dtype),
        "dst": rng.random(SSYM * len_1d).astype(dtype),
        "out": np.zeros(1, dtype=dtype),
        "threshold_data": rng.random(len_1d).astype(dtype),
        "a_2d": arr_2d.ravel().copy(), "b_2d": arr_2d.ravel().copy(),
        "a_3d": arr_3d.ravel().copy(), "b_3d": arr_3d.ravel().copy(),
        "ip": idx_arr.copy(), "idx": idx_arr.copy(),
        "index": idx_arr.copy(), "ind": idx_arr.copy(),
        "mask": rng.integers(0, 2, size=len_1d, dtype=np.int64),
        "scale": 1.0, "alpha": 1.0, "beta": 0.5, "gamma": 0.25,
        "s": 1.0, "t": 1.0,
        "n": len_1d, "m": len_1d,
        "len_1d": len_1d, "LEN_1D": len_1d,
        "LEN_2D": dim_2d, "LEN_3D": dim_3d,
        "len_2d": dim_2d, "len_3d": dim_3d,
        "ntimes": len_1d, "iterations": len_1d,
        "K": 1, "k": 1, "k1": 1, "k2": len_1d // 4,
        "SSYM": SSYM, "ssym": SSYM,
        "S": S_TILE, "T": T_TILE,
        "s_tile": S_TILE, "t_tile": T_TILE, "tile_size": T_TILE,
        "stride": 4, "offset": 1, "wrap_size": len_1d,
        "nx": dim_3d, "ny": dim_3d, "nz": dim_3d, "nt": 2,
        "t1": 64, "t2": 8, "T1": 64, "T2": 8,
        "vlen": 8, "n1": 1, "n3": len_1d - 1, "inc": 1,
        "M": len_1d // 4, "s1": 1.0, "s2": 2.0, "threshold": 0.5, "j": 0,
        "sum_out": np.zeros(1, dtype=dtype),
        "result": np.zeros(1, dtype=dtype),
        "result_out": np.zeros(1, dtype=dtype),
        "dot": np.zeros(1, dtype=dtype),
        "dot_out": np.zeros(1, dtype=dtype),
        "flat": rng.random(dim_2d * dim_2d).astype(dtype),
        "flat_2d_array": rng.random(dim_2d * dim_2d).astype(dtype),
        "indx": np.mod(np.arange(len_1d, dtype=np.int32) * 7 + 3, len_1d).astype(np.int32),
    }


# ── kwargs builder ─────────────────────────────────────────────────────────────
def _build_dace_kwargs(sdfg, pool: dict) -> "tuple[Optional[dict], list[str]]":
    kwargs: dict = {}
    missing: list[str] = []
    for name, arr_desc in sdfg.arrays.items():
        if arr_desc.transient:
            continue
        val = pool.get(name)
        if val is None:
            missing.append(name)
        else:
            kwargs[name] = val
    for sym_name in sdfg.free_symbols:
        sym_str = str(sym_name)
        if sym_str not in kwargs and sym_str in pool:
            kwargs[sym_str] = pool[sym_str]
    if missing:
        return None, missing
    return kwargs, []


# ── Per-kernel timing worker ───────────────────────────────────────────────────
def _time_one_kernel(args_tuple):
    """
    Compile (if needed) and time a single DaCe kernel.

    Returns (stem, base, (median_us, min_us, stdev_us, vec_info, raw_timings_us))
    on success, or (stem, None, error_message) on failure.
    """
    kdir, reps, is_float, len_1d = args_tuple
    import re as _re, pathlib, time as _t, statistics as _stats
    import numpy as np

    stem = kdir.name
    base = _re.sub(r"_(d|f)(_single)?$", "", stem)

    try:
        import dace, dace.dtypes, dace.config
    except ImportError:
        return stem, None, "dace not importable"

    dace.config.Config.set("compiler", "allow_view_arguments", value=True)
    homebrew_omp = pathlib.Path("/opt/homebrew/opt/libomp")
    if homebrew_omp.exists():
        inc = str(homebrew_omp / "include")
        lib = str(homebrew_omp / "lib")
        existing = dace.config.Config.get("compiler", "cpu", "args") or ""
        if inc not in existing:
            dace.config.Config.set(
                "compiler", "cpu", "args",
                value=f"{existing} -I{inc} -L{lib} -lomp",
            )

    pool = _make_array_pool(len_1d, is_float)

    sdfg_path = kdir / "program.sdfgz"
    try:
        sdfg = dace.SDFG.from_file(str(sdfg_path))
    except Exception as exc:
        return stem, None, f"load SDFG failed: {exc}"

    kwargs, missing = _build_dace_kwargs(sdfg, pool)
    if kwargs is None:
        return stem, None, f"unresolved args: {missing}"

    sdfg.build_folder = str(kdir / "build")
    sdfg.instrument = dace.dtypes.InstrumentationType.No_Instrumentation

    try:
        csdfg = sdfg.compile()
    except Exception as exc:
        return stem, None, f"compile failed: {exc}"

    _generate_rpt_for_kernel(kdir, extra_flags=_extra_flags_from_env())
    vec_info = _vec_info_for_kernel(kdir)

    try:
        csdfg(**kwargs)  # warm-up (not timed)
        timings_us = []
        for _ in range(reps):
            t0 = _t.perf_counter_ns()
            csdfg(**kwargs)
            timings_us.append((_t.perf_counter_ns() - t0) / 1e3)  # ns → µs

        median_us = _stats.median(timings_us)
        min_us    = min(timings_us)
        stdev_us  = _stats.stdev(timings_us) if reps > 1 else 0.0
        return stem, base, (median_us, min_us, stdev_us, vec_info, timings_us)
    except Exception as exc:
        return stem, None, f"run failed: {exc}"


# ── Timing phase ───────────────────────────────────────────────────────────────
_DEFAULT_KERNEL_TIMEOUT = 180


def run_dace_timing_phase(
    build_dir: pathlib.Path,
    out_path: pathlib.Path,
    pattern: str,
    reps: int,
    len_1d: int,
    src_root: "pathlib.Path | None" = None,
    kernel_timeout: int = _DEFAULT_KERNEL_TIMEOUT,
    raw_path: "pathlib.Path | None" = None,
) -> None:
    is_float = bool(re.search(r"_f(_single)?\.py$", pattern))

    kernel_dirs = sorted(
        d for d in build_dir.iterdir()
        if d.is_dir() and (d / "program.sdfgz").exists()
    )
    print(f"  [timing] Found {len(kernel_dirs)} compiled DaCe kernel folders", flush=True)

    rows: list[tuple] = []
    raw_rows: list[tuple] = []
    skipped = 0
    mismatches = 0
    work = [(kdir, reps, is_float, len_1d) for kdir in kernel_dirs]

    pool = multiprocessing.Pool(processes=1)
    try:
        for item in work:
            kdir = item[0]
            stem = kdir.name
            print(f"  [timing] submitting {stem} ...", flush=True)

            async_result = pool.apply_async(_time_one_kernel, (item,))
            try:
                result = async_result.get(timeout=kernel_timeout)
                stem_r, base, payload = result
                if base is None:
                    print(f"  [timing] SKIP {stem_r} — {payload}", flush=True)
                    skipped += 1
                else:
                    median_us, min_us, stdev_us, vec_info, timings_us = payload
                    vec_tag = "VEC" if vec_info["vectorized"] else "---"
                    mismatch_tag = ""
                    if vec_info.get("remark_mismatch"):
                        mismatch_tag = "  [MISMATCH: remark disagreed with assembly]"
                        mismatches += 1
                    print(
                        f"  [timing] ok   {stem_r}  "
                        f"median={median_us:.1f}µs  min={min_us:.1f}µs  [{vec_tag}]{mismatch_tag}",
                        flush=True,
                    )
                    rows.append((base, median_us, min_us, stdev_us, vec_info))
                    for rep_idx, t_us in enumerate(timings_us):
                        raw_rows.append((base, rep_idx, t_us))

            except multiprocessing.TimeoutError:
                print(f"  [timing] SKIP {stem} — timed out after {kernel_timeout}s", flush=True)
                skipped += 1
                pool.terminate(); pool.join()
                pool = multiprocessing.Pool(processes=1)

            except Exception as exc:
                print(f"  [timing] SKIP {stem} — worker error: {exc}", flush=True)
                skipped += 1
                pool.terminate(); pool.join()
                pool = multiprocessing.Pool(processes=1)

    finally:
        pool.terminate()
        pool.join()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["kernel,median_us,min_us,stdev_us,vectorized,vec_count,missed_count,remark_vectorized,remark_mismatch"]
    for kernel, med, mn, std, vec_info in sorted(rows, key=lambda r: r[0]):
        lines.append(
            f"{kernel},{med:.1f},{mn:.1f},{std:.1f},"
            f"{'1' if vec_info['vectorized'] else '0'},"
            f"{vec_info['vec_count']},"
            f"{vec_info['missed_count']},"
            f"{'1' if vec_info.get('remark_vectorized') else '0'},"
            f"{'1' if vec_info.get('remark_mismatch') else '0'}"
        )
    out_path.write_text("\n".join(lines) + "\n")

    if raw_path is None:
        raw_path = out_path.with_name(out_path.stem + "_raw_timings.csv")
    raw_path = pathlib.Path(raw_path)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_lines = ["kernel,rep,timing_us"]
    for kernel, rep_idx, t_us in raw_rows:
        raw_lines.append(f"{kernel},{rep_idx},{t_us:.3f}")
    raw_path.write_text("\n".join(raw_lines) + "\n")

    print(f"  [timing] {len(rows)} kernels timed, {skipped} skipped -> {out_path}")
    if mismatches:
        print(f"  [timing] WARNING: {mismatches} kernel(s) had remark/assembly vectorization mismatches")
    print(f"  [timing] raw timings ({len(raw_rows)} rows) -> {raw_path}", flush=True)


# ── Compilation helpers ────────────────────────────────────────────────────────
def _compile_one(args_tuple):
    """
    Compile one DaCe kernel to SDFGZ + shared library via an isolated subprocess.
    Returns: (stem, success, message)
    """
    py_file, build_dir, force = args_tuple
    stem      = py_file.stem
    kdir      = build_dir / stem
    sdfg_path = kdir / "program.sdfgz"

    extra = _extra_flags_from_env()

    if sdfg_path.exists() and not force:
        _generate_rpt_for_kernel(kdir, extra_flags=extra)
        return stem, True, "cached"

    kdir.mkdir(parents=True, exist_ok=True)
    script_lines = [
        "import sys, pathlib, dace, importlib.util",
        "kdir = pathlib.Path(" + repr(str(kdir)) + ")",
        "kdir.mkdir(parents=True, exist_ok=True)",
        "dace.config.Config.set('default_build_folder', value=str(kdir / 'build'))",
        "spec = importlib.util.spec_from_file_location(" + repr(stem) + ", " + repr(str(py_file)) + ")",
        "mod  = importlib.util.module_from_spec(spec)",
        "spec.loader.exec_module(mod)",
        "prog = next(",
        "    (getattr(mod, a) for a in dir(mod)",
        "     if not a.startswith('_') and hasattr(getattr(mod, a, None), 'to_sdfg')),",
        "    None,",
        ")",
        "if prog is None:",
        "    raise RuntimeError('no @dace.program found')",
        "sdfg = prog.to_sdfg()",
        "sdfg.save(str(kdir / 'program.sdfgz'))",
        "sdfg.compile()",
    ]
    try:
        result = subprocess.run(
            [sys.executable, "-c", "\n".join(script_lines)],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            err = result.stderr.strip().splitlines()
            return stem, False, err[-1] if err else "unknown error"

        _generate_rpt_for_kernel(kdir, extra_flags=extra)
        return stem, True, "compiled"

    except subprocess.TimeoutExpired:
        return stem, False, "timeout"
    except Exception as exc:
        return stem, False, str(exc)


# ── Public API ─────────────────────────────────────────────────────────────────
def compile_dace_all(
    src_root: "str | pathlib.Path",
    build_dir: "str | pathlib.Path",
    pattern: str = "*.py",
    force: bool = False,
    jobs: int = 0,
) -> dict:
    src_root  = pathlib.Path(src_root).resolve()
    build_dir = pathlib.Path(build_dir).resolve()
    j = jobs if jobs > 0 else multiprocessing.cpu_count()
    all_py = sorted(src_root.glob("**/*.py"))
    kernel_files = [
        f for f in all_py
        if fnmatch.fnmatch(f.name, pattern) and not f.name.startswith("_")
    ]
    work = [(f, build_dir, force) for f in kernel_files]
    if j == 1:
        results = [_compile_one(item) for item in work]
    else:
        with multiprocessing.Pool(processes=j) as p:
            results = p.map(_compile_one, work)
    ok  = [stem for stem, s, _ in results if s]
    err = {stem: msg for stem, s, msg in results if not s}
    return {"compiled": ok, "failed": err, "total": len(kernel_files)}


def parse_dace_vec_reports(build_dir: "str | pathlib.Path") -> dict:
    build_dir = pathlib.Path(build_dir)
    reports: dict[str, dict] = {}
    for kdir in build_dir.iterdir():
        if not kdir.is_dir():
            continue
        if not (kdir / "program.sdfgz").exists():
            continue
        reports[kdir.name] = _vec_info_for_kernel(kdir)
    return reports


# ── Main ───────────────────────────────────────────────────────────────────────
def main_compile_dace(
    default_root: str = "tsvc_2/tsvc_dace_microkernels",
    default_build_dir: str = ".dace_build",
    argv: "list | None" = None,
) -> int:
    ap = argparse.ArgumentParser(description="Compile (and optionally time) DaCe TSVC kernel files.")
    ap.add_argument("root", metavar="SRC_ROOT")
    ap.add_argument("-b", "--build-dir", default=default_build_dir, metavar="DIR")
    ap.add_argument("--pattern", default="*.py", metavar="GLOB")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--time", action="store_true")
    ap.add_argument("--reps", type=int, default=30, metavar="N")
    ap.add_argument("--len-1d", type=int, default=1024, metavar="N", dest="len_1d")
    ap.add_argument("-j", type=int, default=multiprocessing.cpu_count(), metavar="N")
    ap.add_argument("--timing-out", default=None, metavar="FILE")
    ap.add_argument("--raw-timing-out", default=None, metavar="FILE",
                    help="Write raw per-repetition timing CSV to FILE. "
                         "Defaults to <timing-out stem>_raw_timings.csv.")
    ap.add_argument("--kernel-timeout", type=int, default=_DEFAULT_KERNEL_TIMEOUT,
                    metavar="SEC", dest="kernel_timeout")
    ap.add_argument("--vec-report", action="store_true",
                    help="Read per-kernel assembly (ground truth) + .rpt files "
                         "and print a vectorization summary, flagging any "
                         "remark/assembly mismatches.")
    ap.add_argument("--vec-report-out", default=None, metavar="FILE")
    args = ap.parse_args(argv)

    src_root  = pathlib.Path(args.root).resolve()
    build_dir = pathlib.Path(args.build_dir).resolve()

    if not src_root.is_dir():
        raise SystemExit(f"ERROR: source root not found: {src_root}")

    all_py = sorted(src_root.glob("**/*.py"))
    kernel_files = [
        f for f in all_py
        if fnmatch.fnmatch(f.name, args.pattern) and not f.name.startswith("_")
    ]
    print(f"Found {len(kernel_files)} DaCe kernel files under {src_root}")

    t0 = _time.perf_counter()
    work = [(f, build_dir, args.force) for f in kernel_files]
    if args.j == 1:
        results = [_compile_one(item) for item in work]
    else:
        with multiprocessing.Pool(processes=args.j) as pool:
            results = pool.map(_compile_one, work)

    ok  = sum(1 for _, s, _ in results if s)
    err = sum(1 for _, s, _ in results if not s)
    for stem, success, msg in results:
        if not success:
            print(f"  [compile] FAIL {stem}: {msg}")
    print(
        f"Compiled {ok}/{len(kernel_files)} kernels"
        + (f" ({err} failed)" if err else "")
        + f" in {_time.perf_counter() - t0:.1f}s"
    )

    if args.time:
        timing_out = (
            pathlib.Path(args.timing_out) if args.timing_out
            else build_dir / "dace.timing_report.csv"
        )
        raw_timing_out = (
            pathlib.Path(args.raw_timing_out) if args.raw_timing_out
            else None
        )
        print(
            f"Running DaCe timing phase "
            f"({args.reps} reps, len_1d={args.len_1d}, "
            f"timeout={args.kernel_timeout}s/kernel) ..."
        )
        t1 = _time.perf_counter()
        run_dace_timing_phase(
            build_dir=build_dir,
            out_path=timing_out,
            pattern=args.pattern,
            reps=args.reps,
            len_1d=args.len_1d,
            src_root=src_root,
            kernel_timeout=args.kernel_timeout,
            raw_path=raw_timing_out,
        )
        print(f"Done in {_time.perf_counter() - t1:.1f}s")

    if args.vec_report:
        vec_results = parse_dace_vec_reports(build_dir)
        vec_count   = sum(1 for v in vec_results.values() if v.get("vectorized"))
        mismatch_count = sum(1 for v in vec_results.values() if v.get("remark_mismatch"))
        header = (
            f"DaCe vectorization report (assembly-verified): "
            f"{vec_count}/{len(vec_results)} kernels with vectorized loops"
        )
        report_lines = [header]
        if mismatch_count:
            report_lines.append(
                f"  *** {mismatch_count} kernel(s) had a remark/assembly mismatch "
                f"(compiler claimed one thing, machine code showed another) ***"
            )
        for name, info in sorted(vec_results.items()):
            tag = "[VEC]" if info.get("vectorized") else "[---]"
            mismatch_flag = " [MISMATCH]" if info.get("remark_mismatch") else ""
            report_lines.append(
                f"  {tag} {name}  "
                f"(vec={info['vec_count']}, missed={info['missed_count']}, "
                f"remark_said_vec={'yes' if info.get('remark_vectorized') else 'no'})"
                f"{mismatch_flag}"
            )
            for remark in info.get("sample_remarks", [])[:3]:
                report_lines.append(f"        {remark}")
        report_text = "\n".join(report_lines)
        print(report_text)
        out_path = (
            pathlib.Path(args.vec_report_out) if args.vec_report_out
            else build_dir / "dace.vec_report.txt"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_text)
        print(f"Saved vec report -> {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main_compile_dace())