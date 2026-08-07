#!/usr/bin/env python3
"""
compile_cloudsc_vec_reports.py

Compile CloudSC SDFGs (DaCe/C++) and their Fortran baselines, generating
vectorization reports for each compiler / cost-model / cpu cell.

Vectorization ground truth
---------------------------
Compiler remarks (GCC -fopt-info-vec-*, Clang -Rpass=loop-vectorize) can be
misleading in BOTH directions:
  - A compiler may emit an "optimized: loop vectorized" remark for a
    transform that a *later* legality/cost-model pass invalidates, leaving
    pure scalar code in the final object (false positive — seen in TSVC
    kernels s231, s2102, s1232).
  - A compiler may vectorize via a DIFFERENT pass than the loop vectorizer
    (e.g. GCC's SLP/basic-block vectorizer) whose success message never
    contains the word "loop", so a text classifier tuned to loop-vectorizer
    phrasing reports it as "not vectorized" even though real SIMD code was
    emitted (false negative — seen in TSVC kernel s116).

To avoid trusting the remark text in either direction, every kernel is now
ALSO compiled with -S to a real assembly file, which is scanned directly for
SIMD register/opcode usage (AArch64 NEON/SVE, x86 AVX/AVX-512). That scan is
the authoritative `vectorized` verdict used in the generated report. The
remark-derived verdict (`summarize_vectorization`) is still computed and
kept for its "reasons" text (which explains WHY something did or didn't
vectorize) — but wherever the two disagree, the report explicitly flags a
MISMATCH instead of silently trusting one source.
"""

from __future__ import annotations


import argparse
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
from typing import Iterable, Optional


previous = 0


ALL_COMPILERS = ("clang", "gcc", "icpx")
ALL_COST_MODELS = ("default", "cheap", "unlimited", "disabled")
ALL_CPUS = (
    "amd_epyc", "amd_epyc_genoa", "apple_m_series",
    "arm_grace", "fugaku_a64fx", "ibm_power", "intel_xeon",
)


_BASE_MODEL_CLANG = "-O3 -march=native -fno-math-errno -fno-trapping-math -fno-signed-zeros"
_BASE_MODEL_GCC = "-O3 -march=native -fno-math-errno -fno-trapping-math -fno-signed-zeros -fno-signaling-nans"


#Has to be -O0, since Clang will override the disbale vector flags when set to -O3.
_BASE_MODEL_CLANG_DISABLED = "-O0 -march=native -fno-math-errno -fno-trapping-math -fno-signed-zeros"



_COST_MODEL_CXXFLAGS = {
    "disabled":  "-fno-vectorize -fno-slp-vectorize",
    # "cheap":     "-fvectorize -mllvm -vectorizer-min-trip-count=64",
    "default":   "-fvectorize",
    "unlimited": "-Rpass-analysis=loop-vectorize",
}
_COST_MODEL_CXXFLAGS_GCC = {
    "disabled":  "-fno-tree-vectorize",
    "cheap":     "-ftree-vectorize -fvect-cost-model=cheap",
    "default":   "-ftree-vectorize -fvect-cost-model=dynamic",
    "unlimited": "-fno-vect-cost-model",
}
_VEC_REMARK_FLAGS = {
    "clang": "-Rpass=.* -Rpass-missed=.*",
    "gcc":   "-fopt-info-all",
    "icpx":  "-Rpass=loop-vectorize -Rpass-missed=loop-vectorize -qopt-report=5 -qopt-report-phase=vec",
}


# Fortran compiler candidates per C++ compiler family (tried in order).
# flang-new is the real LLVM Fortran driver; many distros ship only that name.
# The bare `flang` on macOS/some distros is a stub that accepts no flags.
_FORTRAN_COMPILER_CANDIDATES = {
    "clang": ["flang-new", "flang"],
    "gcc":   ["gfortran"],
    "icpx":  ["ifx", "ifort"],
}


_FORTRAN_VEC_FLAGS = {
    "clang": "-Rpass=loop-vectorize -Rpass-missed=loop-vectorize -Rpass-analysis=loop-vectorize",
    "gcc":   "-fopt-info-vec-all",
    "icpx":  "-Rpass=loop-vectorize -Rpass-missed=loop-vectorize -qopt-report=5 -qopt-report-phase=vec",
}


_FORTRAN_OPT_FLAGS = {
    "disabled":  "-O0 -march=native -fno-vectorize",
    "default":   "-O3 -march=native -fvectorize",
    "unlimited": "-O3 -march=native",
}


_FORTRAN_OPT_FLAGS_GCC = {
    "disabled":  "-O3 -march=native -fno-tree-vectorize",
    "cheap":     "-O3 -march=native -fvect-cost-model=cheap",
    "default":   "-O3 -march=native -fvect-cost-model=dynamic",
    "unlimited": "-O3 -march=native -fno-vect-cost-model",
}


# VEC_HIT_RE = re.compile(r"(optimized: loop vectorized|loop vectorized using|loop vectorized$|vectorized loop \(|LOOP AUTO-VECTORIZED|interleaved loop)", re.IGNORECASE)
# VEC_MISS_RE = re.compile(r"(missed:|not vectorized|loop not vectorized|vectorization is possible but not beneficial|could not be vectorized|not beneficial)", re.IGNORECASE)
# WHY_RE = re.compile(r"(remark:|missed:|not vectorized|unsafe|dependen|cannot|could not|cost-model|beneficial|vectorized)", re.IGNORECASE)


# VEC_HIT_RE = re.compile(r"(vectorized loop|optimized: loop vectorized|remark: interleaved loop)", re.IGNORECASE)
# VEC_MISS_RE = re.compile(r"(missed: couldn't|remark: loop not vectorized)", re.IGNORECASE)
# WHY_RE = re.compile(r"(missed: not vectorized:|optimized:  loop versioned|remark: the cost-model indicates|remark: loop not vectorized:)", re.IGNORECASE)


VEC_HIT_RE = re.compile(r"(remark:\s*(vectorized loop|interleaved loop)|optimized: loop vectorized using)", re.IGNORECASE)
VEC_MISS_RE = re.compile(r"(remark:\s*loop not vectorized(?!:)|missed: couldn't vectorize loop)", re.IGNORECASE)
WHY_RE = re.compile(
    r"(remark:\s*loop not vectorized:|missed: not vectorized:|optimized:\s*loop versioned|"
    r"remark:\s*the cost-model indicates|Unsafe indirect dependence|"
    r"cannot vectorize outer loop|outer loop cannot|has inner loop)",
    re.IGNORECASE,
)


# ── Assembly-based ground-truth vectorization detection ───────────────────────
# AArch64: NEON vector registers (v0.2d, v1.16b, ...), SVE Z/P registers
# (z0.d, p7/z), quad registers used for 128-bit vector load/store/move (q0),
# and SVE-specific mnemonics (predicate generation, structured loads, etc).
_AARCH64_VEC_RE = re.compile(
    r"\bv\d{1,2}\.\d*[bhsd]\b"                 # NEON vector reg w/ arrangement: v0.2d, v12.4s
    r"|\bz\d{1,2}\.[bhsd]\b"                   # SVE Z register: z0.d, z26.d
    r"|\bp\d{1,2}/[zm]\b"                      # SVE predicate governing a vector op: p7/z
    r"|\bq\d{1,2}\b"                           # 128-bit quad register (vector load/store/move)
    r"|\b(ld[1-4][bhwd]?|st[1-4][bhwd]?)\b"    # (SVE/NEON) structured / scalable load-store
    r"|\bwhilelo\b|\bwhilelt\b|\bwhilels\b|\bwhilehs\b|\bwhilege\b|\bwhilegt\b"
    r"|\bptrue\b|\bpfalse\b|\bmovprfx\b|\bfadda\b|\bfaddv\b|\blastb\b|\blasta\b"
    r"|\bcntb\b|\bcntd\b|\bcnth\b|\bcntw\b"
    r"|\buzp[12]\b|\bzip[12]\b|\bext\s+v\d"    # NEON shuffle instructions (SLP realignment)
    r"|\bvect__?\d",                            # GCC SLP-vectorizer synthetic var names (fallback text form)
    re.IGNORECASE,
)

# x86: ymm/zmm registers are always vector (256/512-bit, never scalar). xmm
# is ambiguous on its own (scalar addsd/mulsd also use xmm), so it only
# counts when paired with a *packed* suffix (ps/pd) rather than scalar
# (ss/sd), or with an explicit FMA-packed mnemonic.
_X86_VEC_RE = re.compile(
    r"%?[yz]mm\d{1,2}\b"
    r"|%?xmm\d{1,2}\b.*\b\w*p[sd]\d*\b"
    r"|\bvfmadd\d{3}p[sd]\b|\bvfmsub\d{3}p[sd]\b",
    re.IGNORECASE,
)

# Symbols that are never the actual kernel loop body (runtime/support code)
# — excluded from the scan so a stray vector instruction there can't
# produce a false "vectorized" verdict for the kernel itself.
_NON_KERNEL_SYMBOL_RE = re.compile(
    r"dace_init|dace_exit|GLOBAL__sub_I|dacestub|_ZdlPv|_Znwm|"
    r"system_clock|chrono",
    re.IGNORECASE,
)

# Matches a function-start label in either objdump disassembly
# ("0000000000000000 <name>:") or raw compiler -S assembly ("name:").
_FUNC_LABEL_RE = re.compile(
    r"^[0-9a-f]{8,16}\s+<(?P<obj_name>[^>]+)>:\s*$"
    r"|^(?P<asm_name>[A-Za-z_$][\w$]*):\s*$"
)


def _split_into_functions(asm_text: str) -> list:
    """Split raw assembly/disassembly text into (symbol_name, body) chunks."""
    chunks = []
    current_name = None
    current_lines: list = []

    for line in asm_text.splitlines():
        m = _FUNC_LABEL_RE.match(line.strip())
        if m:
            if current_name is not None:
                chunks.append((current_name, "\n".join(current_lines)))
            current_name = m.group("obj_name") or m.group("asm_name")
            current_lines = []
        else:
            current_lines.append(line)

    if current_name is not None:
        chunks.append((current_name, "\n".join(current_lines)))

    if not chunks:
        chunks = [("<unknown>", asm_text)]

    return chunks


def _parse_vec_from_asm(asm_text: str, *, kernel_functions_only: bool = True) -> dict:
    """
    Ground-truth vectorization check: scan actual assembly/machine code for
    SIMD register/instruction usage, rather than trusting compiler remarks.
    """
    functions = _split_into_functions(asm_text)
    vec_lines: list = []

    for name, body in functions:
        if kernel_functions_only and _NON_KERNEL_SYMBOL_RE.search(name):
            continue
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if _AARCH64_VEC_RE.search(stripped) or _X86_VEC_RE.search(stripped):
                vec_lines.append(stripped)

    return {
        "vectorized":  len(vec_lines) > 0,
        "vec_count":   len(vec_lines),
        "samples":     vec_lines[:5],
    }


def _asm_verdict_from_file(asm_file: pathlib.Path) -> Optional[dict]:
    if not asm_file.exists():
        return None
    try:
        text = asm_file.read_text(errors="replace")
    except Exception:
        return None
    return _parse_vec_from_asm(text)


def _strip_mllvm_flags(flags_str: str) -> str:
    """Remove -mllvm <arg> pairs from a flag string.


    -mllvm requires two separate tokens, which works when cmake splits
    CXXFLAGS by spaces, but breaks when the whole string is passed as a
    single value via DACE_compiler_cpu_args."""
    tokens = flags_str.split()
    out = []
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if tok == "-mllvm":
            skip_next = True
            continue
        out.append(tok)
    return " ".join(out)



def _source_env(script_path: pathlib.Path) -> dict:
    result = subprocess.run(
        ["bash", "-c", f"source {script_path} && env"],
        capture_output=True, text=True, check=True,
    )
    env = {**os.environ}
    for line in result.stdout.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            env[k] = v
    return env



def _build_env(env: dict, compiler: str, cost_model: str) -> dict:
    env = dict(env)
    if platform.system() == "Darwin":
        if compiler == "clang":
            env["CXX"] = "clang++"
            env["CXX_COMPILER"] = "clang"
            env["DACE_compiler_cpu_executable"] = "clang++"
        elif compiler == "gcc":
            env["CXX"] = "/opt/homebrew/bin/g++-15"
            env["CXX_COMPILER"] = "gcc"
            env["DACE_compiler_cpu_executable"] = "/opt/homebrew/bin/g++-15"


    opt_flags = (_COST_MODEL_CXXFLAGS_GCC if compiler == "gcc" else _COST_MODEL_CXXFLAGS).get(cost_model, "")
    remark_flags = _VEC_REMARK_FLAGS.get(compiler, "")


    if compiler == "gcc":
        base_and_opt = f"{_BASE_MODEL_GCC} {opt_flags}".strip()
    else:
        if cost_model == "disabled":
            base_and_opt = f"{_BASE_MODEL_CLANG_DISABLED} {opt_flags}".strip()
        else:
            base_and_opt = f"{_BASE_MODEL_CLANG} {opt_flags}".strip()


    # Put existing CXXFLAGS FIRST, then our base+opt flags LAST so
    # cost-model flags (e.g. -fno-vectorize) always win the "last flag wins"
    # resolution clang applies to conflicting -f(no-)vectorize toggles.
    existing = env.get("CXXFLAGS", "").strip()
    if base_and_opt:
        env["CXXFLAGS"] = f"{existing} {base_and_opt}".strip()
    if remark_flags:
        env["CXXFLAGS"] = f"{env.get('CXXFLAGS', '')} {remark_flags}".strip()
        env["DACE_compiler_cpu_args"] = f"{env.get('DACE_compiler_cpu_args', '')} {_strip_mllvm_flags(base_and_opt)} {remark_flags}".strip()
    return env



def ensure_env_script(name: str, compiler: str, cost_model: str, cpu: str) -> pathlib.Path:
    scripts_dir = pathlib.Path("scripts")
    scripts_dir.mkdir(exist_ok=True)
    script_path = scripts_dir / f"source.{name}.sh"
    if not script_path.exists():
        subprocess.run([
            "vectra-source-sh",
            "--compiler", compiler,
            "--cost-model", cost_model,
            "--cpu", cpu,
            "--out", str(script_path),
        ], check=True)
    return script_path



def discover_sdfgs(root: pathlib.Path) -> list[tuple[str, pathlib.Path, pathlib.Path]]:
    found = []
    for path in sorted(root.rglob("*.sdfg")):
        if path.name.startswith("run_"):
            continue
        if path.parent.name == "harness":
            continue
        bench_dir = path.parent
        bench_name = bench_dir.name
        found.append((bench_name, bench_dir, path))
    return found



def collect_texts(run_dir: pathlib.Path, proc: subprocess.CompletedProcess | None) -> str:
    parts: list[str] = []
    if proc is not None:
        parts.extend([proc.stdout or "", "\n", proc.stderr or ""])
    for pattern in ("*.rpt", "*.opt.yaml", "*.optrpt", "*.txt"):
        for p in sorted(run_dir.rglob(pattern)):
            if p.name in {"summary.txt", "stdout.txt", "stderr.txt", "report_driver.py"}:
                continue
            try:
                parts.extend([f"\n\n===== {p.relative_to(run_dir)} =====\n", p.read_text(errors="replace")])
            except Exception:
                pass
    return "".join(parts)



_LOC_RE = re.compile(r"^([^:]+):(\d+):(\d+)")


def _count_unique_locations(lines: list[str], kernel_cpp: str | None = None) -> int:
    locs: set[str] = set()
    for s in lines:
        m = _LOC_RE.match(s)
        if not m:
            continue
        filepath = m.group(1)
        if kernel_cpp and not filepath.endswith(kernel_cpp):
            continue
        locs.add(m.group())
    return len(locs)



def summarize_vectorization(text: str, kernel_cpp: str | None = None) -> tuple[str, list[str], int, int]:
    """Remark-text-based verdict. NOT ground truth — see module docstring.
    Kept for its 'reasons' text (why something did/didn't vectorize) and
    combined with the assembly-based verdict by the caller."""
    hits, misses, why = [], [], []
    lines = text.splitlines()


    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue


        if VEC_HIT_RE.search(s):
            hits.append(s)
        elif VEC_MISS_RE.search(s):
            misses.append(s)
        # Attach "why" reasoning found on this or the immediately following
        # continuation line (clang splits detail onto a second line for
        # "unsafe dependent memory operations" remarks).
        if WHY_RE.search(s):
            why.append(s)
        elif i + 1 < len(lines) and WHY_RE.search(lines[i + 1].strip()):
            why.append(lines[i + 1].strip())


    vec_count = _count_unique_locations(hits, kernel_cpp)
    miss_count = _count_unique_locations(misses, kernel_cpp)


    if hits:
        return "yes", (hits + misses + why)[:12], vec_count, miss_count
    if misses:
        return "no", (misses + why)[:12], vec_count, miss_count
    if why == 0:
        return f"0/{previous}, disabled version, no vectorisation"
    return "no", ([*why][:12] or ["0/1 loops vectorized (1 not vectorized)"]), 0, 0



def copy_reports(build_folder: pathlib.Path, out_dir: pathlib.Path) -> None:
    for pattern in ("*.rpt", "*.opt.yaml", "*.optrpt"):
        for src in build_folder.rglob(pattern):
            rel = src.relative_to(build_folder)
            dst = out_dir / "raw_reports" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src, dst)
            except Exception:
                pass



_FLAGS_MAKE_CXX_RE = re.compile(r"^(CXX_FLAGS(?:arm64)?\s*=.*)$", re.MULTILINE)
_REMARK_FLAG_RE = re.compile(r"-Rpass\S*|-fopt-info\S*|-qopt-report\S*")



def _override_flags(cxxflags: str) -> str:
    """Strip diagnostic/remark flags from CXXFLAGS; the remainder are the
    cost-model flags that must appear LAST in the compiler invocation to
    override cmake's appended -O2 -g -DNDEBUG (from RelWithDebInfo)."""
    stripped = _REMARK_FLAG_RE.sub("", cxxflags)
    # Also strip -mllvm <arg> pairs — they need to be adjacent tokens and
    # cmake's flags.make splitting makes re-appending them safe, but they
    # are already present from the original CXXFLAGS entry.
    tokens = stripped.split()
    out, skip = [], False
    for tok in tokens:
        if skip:
            skip = False
            out.append(tok)
            continue
        if tok == "-mllvm":
            skip = True
            out.append(tok)
            continue
        out.append(tok)
    return " ".join(out).strip()



def _patch_flags_make(cmake_build: pathlib.Path, cxxflags: str) -> None:
    """Re-append cost-model flags at the end of every flags.make CXX_FLAGS
    line so they take precedence over cmake's own appended build-type flags.


    DaCe hardcodes CMAKE_BUILD_TYPE=RelWithDebInfo, causing cmake to append
    '-O2 -g -DNDEBUG' AFTER CMAKE_CXX_FLAGS in every flags.make.  In clang
    and gcc, a later -O<n> overrides earlier ones, and -O2 re-enables
    vectorization even if -fno-vectorize appeared before it.  Appending our
    flags last ensures they are always the final word."""
    append = _override_flags(cxxflags)
    if not append:
        return
    for flags_file in cmake_build.rglob("flags.make"):
        original = flags_file.read_text()
        patched = _FLAGS_MAKE_CXX_RE.sub(lambda m: m.group(1) + " " + append, original)
        if patched != original:
            flags_file.write_text(patched)



def recompile_for_remarks(build_folder: pathlib.Path, out_dir: pathlib.Path, env: dict) -> None:
    """Re-run make in the cmake build dir after deleting .o files so clang/gcc
    vectorization remarks (which DaCe's subprocess swallows) are captured to
    vec_remarks.rpt, which collect_texts already picks up via *.rpt."""
    cmake_build = build_folder / "build"
    if not cmake_build.is_dir():
        return
    # Patch flags.make so our cost-model flags appear AFTER cmake's appended
    # -O2 -g -DNDEBUG (RelWithDebInfo). This applies to all cost models:
    # unlimited/-O3, cheap/-O1, disabled/-fno-vectorize are all overridden
    # by cmake's -O2 without this patch.
    _patch_flags_make(cmake_build, env.get("CXXFLAGS", ""))
    # Force recompile by removing object files
    for o_file in cmake_build.rglob("*.o"):
        try:
            o_file.unlink()
        except OSError:
            pass
    proc = subprocess.run(
        ["make", "--no-print-directory"],
        cwd=cmake_build,
        capture_output=True,
        text=True,
        env=env,
    )
    remarks = proc.stderr + proc.stdout
    (out_dir / "vec_remarks.rpt").write_text(remarks)


# ── Assembly ground-truth generation for the DaCe/C++ path ────────────────────
_FLAGS_MAKE_COMPILER_RE = re.compile(r"^#\s*compile\s+CXX\s+with\s+(\S+)", re.MULTILINE)


def _parse_flags_make_for_asm(flags_make: pathlib.Path) -> tuple[str, list[str], list[str], list[str]]:
    """Return (compiler_exe, cxx_flags, cxx_defines, cxx_includes) from a
    single flags.make file, for re-invoking the compiler with -S."""
    compiler_exe = ""
    cxx_flags: list[str] = []
    cxx_defines: list[str] = []
    cxx_includes: list[str] = []

    text = flags_make.read_text(errors="ignore")

    m = _FLAGS_MAKE_COMPILER_RE.search(text)
    if m:
        compiler_exe = m.group(1)

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


def _find_kernel_source_and_flags_make(
    cmake_build: pathlib.Path, kernel_stem: str
) -> tuple[Optional[pathlib.Path], Optional[pathlib.Path]]:
    """Locate the kernel's own .cpp source file (preferring an exact stem
    match, excluding dacestub) and the flags.make governing its compile
    unit, under a DaCe-generated cmake build tree."""
    src_cpp: Optional[pathlib.Path] = None
    exact_matches = [
        c for c in cmake_build.rglob(f"{kernel_stem}*.cpp")
        if "dacestub" not in c.name
    ]
    if exact_matches:
        src_cpp = max(exact_matches, key=lambda p: len(p.parts))
    else:
        cpu_matches = sorted(cmake_build.rglob("src/cpu/*.cpp"), key=lambda p: len(p.parts), reverse=True)
        if cpu_matches:
            src_cpp = cpu_matches[0]
        else:
            for c in cmake_build.rglob("*.cpp"):
                if "CMakeFiles" in str(c) or "/sample/" in str(c):
                    continue
                src_cpp = c
                break

    if src_cpp is None:
        return None, None

    flags_make: Optional[pathlib.Path] = None
    candidates = [f for f in cmake_build.rglob("flags.make") if "dacestub" not in f.parts[-2]]
    if candidates:
        flags_make = max(candidates, key=lambda p: len(p.parts))
    elif list(cmake_build.rglob("flags.make")):
        flags_make = max(cmake_build.rglob("flags.make"), key=lambda p: len(p.parts))

    return src_cpp, flags_make


def generate_dace_asm(build_folder: pathlib.Path, out_dir: pathlib.Path, sdfg_stem: str, env: dict) -> Optional[pathlib.Path]:
    """
    Recompile the DaCe-generated kernel .cpp with -S to obtain real
    assembly, written to out_dir/vec_check.s. This is what
    `_parse_vec_from_asm` treats as ground truth. Returns the path on
    success, or None if the source/flags.make couldn't be located.
    """
    cmake_build = build_folder / "build"
    if not cmake_build.is_dir():
        return None

    src_cpp, flags_make = _find_kernel_source_and_flags_make(cmake_build, sdfg_stem)
    if src_cpp is None or flags_make is None:
        return None

    compiler_exe, cxx_flags, cxx_defines, cxx_includes = _parse_flags_make_for_asm(flags_make)
    if not compiler_exe:
        compiler_exe = env.get("DACE_compiler_cpu_executable", "g++")

    asm_out = out_dir / "vec_check.s"
    cmd = (
        [compiler_exe]
        + cxx_defines
        + cxx_includes
        + cxx_flags
        + ["-S", "-o", str(asm_out), str(src_cpp.resolve())]
    )

    try:
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(flags_make.parent.resolve()),
            env=env,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None

    return asm_out if asm_out.exists() else None



def compile_sdfg(sdfg_path: pathlib.Path, out_dir: pathlib.Path, env: dict) -> tuple[int, str, list[str], int, int, bool, bool]:
    """
    Returns (returncode, status, reasons, vec_count, miss_count,
             remark_mismatch, asm_vectorized).

    `status`/`vec_count`/`miss_count` are remark-derived (as before, for the
    "why" reasoning). `asm_vectorized` is the assembly-verified ground
    truth. `remark_mismatch` is True whenever the remark-derived status
    disagrees with `asm_vectorized`.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    build_folder = out_dir / "build"
    build_folder.mkdir(parents=True, exist_ok=True)


    driver = out_dir / "report_driver.py"
    driver.write_text(
        "import os\n"
        "import pathlib\n"
        "import dace\n"
        f"sdfg = dace.SDFG.from_file(r'{str(sdfg_path)}')\n"
        "sdfg.build_folder = str(pathlib.Path(r'" + str(build_folder) + "'))\n"
        "sdfg.compile()\n"
    )


    proc = subprocess.run([sys.executable, str(driver)], capture_output=True, text=True, env=env)
    (out_dir / "stdout.txt").write_text(proc.stdout)
    (out_dir / "stderr.txt").write_text(proc.stderr)


    asm_file: Optional[pathlib.Path] = None
    if proc.returncode == 0:
        recompile_for_remarks(build_folder, out_dir, env)
        asm_file = generate_dace_asm(build_folder, out_dir, sdfg_path.stem, env)


    copy_reports(build_folder, out_dir)
    merged = collect_texts(out_dir, proc)
    (out_dir / "summary.txt").write_text(merged)
    # Use only vec_remarks.rpt for counting (avoids double-counting from DaCe's
    # internal compile pass) and restrict to the kernel's own .cpp file (avoids
    # counting dacestub.cpp loops as kernel loops).
    rpt_path = out_dir / "vec_remarks.rpt"
    count_text = rpt_path.read_text(errors="replace") if rpt_path.exists() else merged
    kernel_cpp = sdfg_path.stem + ".cpp"
    status, reasons, vec_count, miss_count = summarize_vectorization(count_text, kernel_cpp)

    asm_verdict = _asm_verdict_from_file(asm_file) if asm_file else None
    asm_vectorized = asm_verdict["vectorized"] if asm_verdict is not None else False
    remark_vectorized = (status == "yes")
    remark_mismatch = (asm_verdict is not None) and (asm_vectorized != remark_vectorized)

    return proc.returncode, status, reasons, vec_count, miss_count, remark_mismatch, asm_vectorized



def compile_fortran(
    f90_path: pathlib.Path,
    out_dir: pathlib.Path,
    compiler: str,
    cost_model: str,
    env: dict,
) -> tuple[int, str, list[str], int, int, bool, bool]:
    """Compile a .f90 file with the Fortran equivalent of *compiler* and
    return (returncode, status, reasons, vec_count, miss_count,
            remark_mismatch, asm_vectorized)."""
    out_dir.mkdir(parents=True, exist_ok=True)


    fc = next(
        (c for c in _FORTRAN_COMPILER_CANDIDATES.get(compiler, []) if shutil.which(c)),
        None,
    )
    if not fc:
        candidates = _FORTRAN_COMPILER_CANDIDATES.get(compiler, [])
        return -1, "unavailable", [f"No Fortran compiler found (tried: {', '.join(candidates)})"], 0, 0, False, False


    opt = (
        _FORTRAN_OPT_FLAGS_GCC if compiler == "gcc" else _FORTRAN_OPT_FLAGS
    ).get(cost_model, "-O3 -march=native")
    vec_flags = _FORTRAN_VEC_FLAGS.get(compiler, "")


    flags = f"{opt} {vec_flags}".split()
    cmd = [fc, *flags, "-c", str(f90_path), "-o", str(out_dir / "kernel.o")]


    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    remarks = proc.stderr + proc.stdout
    (out_dir / "stdout.txt").write_text(proc.stdout)
    (out_dir / "stderr.txt").write_text(proc.stderr)
    (out_dir / "vec_remarks.rpt").write_text(remarks)


    status, reasons, vec_count, miss_count = summarize_vectorization(remarks)

    # Ground-truth assembly pass: same flags, swap -c/-o object output for
    # -S text-assembly output. Skipped gracefully if this second invocation
    # fails for any reason — asm_vectorized just stays False and no
    # mismatch is flagged (nothing to compare against).
    asm_out = out_dir / "vec_check.s"
    asm_verdict = None
    try:
        asm_cmd = [fc, *flags, "-S", str(f90_path), "-o", str(asm_out)]
        asm_proc = subprocess.run(asm_cmd, capture_output=True, text=True, env=env, timeout=120)
        if asm_proc.returncode == 0 and asm_out.exists():
            asm_verdict = _asm_verdict_from_file(asm_out)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    asm_vectorized = asm_verdict["vectorized"] if asm_verdict is not None else False
    remark_vectorized = (status == "yes")
    remark_mismatch = (asm_verdict is not None) and (asm_vectorized != remark_vectorized)

    return proc.returncode, status, reasons, vec_count, miss_count, remark_mismatch, asm_vectorized



def parse_args(argv: Iterable[str] | None = None):
    ap = argparse.ArgumentParser(description="Compile CloudSC SDFGs and generate vectorization reports.")
    ap.add_argument("--root", default="cloudsc_variants", help="Root folder containing benchmark subfolders.")
    ap.add_argument("--compilers", nargs="+", default=["clang"], choices=ALL_COMPILERS)
    ap.add_argument("--cost-models", nargs="+", default=["default"], choices=ALL_COST_MODELS)
    ap.add_argument("--cpus", nargs="+", default=["apple_m_series"], choices=ALL_CPUS)
    ap.add_argument("--pattern", default="*.sdfg", help="Glob pattern for SDFG discovery. Default: *.sdfg")
    return ap.parse_args(argv)



def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    root = pathlib.Path(args.root)
    if not root.exists():
        print(f"Root folder not found: {root}", file=sys.stderr)
        return 2


    sdfgs = [x for x in discover_sdfgs(root) if x[2].match(args.pattern) or args.pattern == "*.sdfg"]
    if not sdfgs:
        print(f"No SDFG files found under {root}", file=sys.stderr)
        return 1


    print(f"Found {len(sdfgs)} SDFG files under {root}")

    total_mismatches = 0

    for bench_name, bench_dir, sdfg_path in sdfgs:
        report_lines = [f"Benchmark: {bench_name}", f"SDFG: {sdfg_path.name}"]


        for compiler in args.compilers:
            for cost_model in args.cost_models:
                if compiler == "clang":
                    if cost_model == "cheap":
                        #There is no clang equivalent for cheap
                        continue
                for cpu in args.cpus:
                    cell = f"{compiler}_{cpu}_{cost_model}"
                    print(f"[{bench_name}] {cell} :: {sdfg_path.name}")
                    script_path = ensure_env_script(cell, compiler, cost_model, cpu)
                    env = _build_env(_source_env(script_path), compiler, cost_model)
                    # print("=== CXXFLAGS ===", env.get("CXXFLAGS"))
                    # print("=== DACE_compiler_cpu_args ===", env.get("DACE_compiler_cpu_args"))
                    out_dir = bench_dir / "vec_reports" / sdfg_path.stem / cell


                    rc, status, reasons, vec_count, miss_count, mismatch, asm_vectorized = compile_sdfg(
                        sdfg_path, out_dir, env
                    )
                    if mismatch:
                        total_mismatches += 1
                    total = vec_count + miss_count
                    count_str = f"{vec_count}/{total} loops vectorized" if total > 0 else "no loop counts available"
                    asm_tag = "yes" if asm_vectorized else "no"
                    mismatch_line = (
                        "  *** MISMATCH: remark-based verdict disagreed with assembly ground truth ***"
                        if mismatch else ""
                    )
                    report_lines.extend([
                        "",
                        f"=== {cell} ===",
                        f"Return code: {rc}",
                        f"Vectorized (assembly-verified, ground truth): {asm_tag}",
                        f"Vectorized (remark-based, diagnostic only): {status}",
                        *( [mismatch_line] if mismatch_line else [] ),
                        f"Loop counts (from remarks): {count_str} ({miss_count} not vectorized)",
                        "Reasons:",
                        *[f"- {r}" for r in reasons],
                        f"Artifacts: vec_reports/{sdfg_path.stem}/{cell}/",
                    ])


                    # ── Fortran baseline ──────────────────────────────────────
                    f90_path = bench_dir / f"{bench_name}.f90"
                    if f90_path.exists():
                        fort_out = bench_dir / "vec_reports" / "fortran" / bench_name / cell
                        (
                            frc, fstatus, freasons, fvec, fmiss,
                            fmismatch, fasm_vectorized,
                        ) = compile_fortran(f90_path, fort_out, compiler, cost_model, env)
                        if fmismatch:
                            total_mismatches += 1
                        ftotal = fvec + fmiss
                        fcount = f"{fvec}/{ftotal} loops vectorized" if ftotal > 0 else "no loop counts available"
                        fasm_tag = "yes" if fasm_vectorized else "no"
                        fmismatch_line = (
                            "  *** MISMATCH: remark-based verdict disagreed with assembly ground truth ***"
                            if fmismatch else ""
                        )
                        report_lines.extend([
                            "",
                            f"--- Fortran baseline ({next(iter(_FORTRAN_COMPILER_CANDIDATES.get(compiler, ['?'])), '?')}) [{cell}] ---",
                            f"Return code: {frc}",
                            f"Vectorized (assembly-verified, ground truth): {fasm_tag}",
                            f"Vectorized (remark-based, diagnostic only): {fstatus}",
                            *( [fmismatch_line] if fmismatch_line else [] ),
                            f"Loop counts (from remarks): {fcount} ({fmiss} not vectorized)",
                            "Reasons:",
                            *[f"- {r}" for r in freasons],
                            f"Artifacts: vec_reports/fortran/{bench_name}/{cell}/",
                        ])
                    else:
                        report_lines.extend([
                            "",
                            f"--- Fortran baseline [{cell}] ---",
                            f"SKIP — {f90_path} not found",
                        ])


        report_path = bench_dir / f"vectorization_report_{sdfg_path.stem}.txt"
        report_path.write_text("\n".join(report_lines) + "\n")
        print(f"Saved {report_path}")

    if total_mismatches:
        print(
            f"\nWARNING: {total_mismatches} cell(s) across all benchmarks had a "
            f"remark/assembly vectorization mismatch — see 'MISMATCH' markers "
            f"in the individual report files.",
            file=sys.stderr,
        )

    return 0



if __name__ == "__main__":
    raise SystemExit(main())