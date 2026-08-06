#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
from typing import Iterable

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


def compile_sdfg(sdfg_path: pathlib.Path, out_dir: pathlib.Path, env: dict) -> tuple[int, str, list[str]]:
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

    if proc.returncode == 0:
        recompile_for_remarks(build_folder, out_dir, env)

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
    return proc.returncode, status, reasons, vec_count, miss_count


def compile_fortran(
    f90_path: pathlib.Path,
    out_dir: pathlib.Path,
    compiler: str,
    cost_model: str,
    env: dict,
) -> tuple[int, str, list[str], int, int]:
    """Compile a .f90 file with the Fortran equivalent of *compiler* and
    return (returncode, status, reasons, vec_count, miss_count)."""
    out_dir.mkdir(parents=True, exist_ok=True)

    fc = next(
        (c for c in _FORTRAN_COMPILER_CANDIDATES.get(compiler, []) if shutil.which(c)),
        None,
    )
    if not fc:
        candidates = _FORTRAN_COMPILER_CANDIDATES.get(compiler, [])
        return -1, "unavailable", [f"No Fortran compiler found (tried: {', '.join(candidates)})"], 0, 0

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
    return proc.returncode, status, reasons, vec_count, miss_count


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

                    rc, status, reasons, vec_count, miss_count = compile_sdfg(sdfg_path, out_dir, env)
                    total = vec_count + miss_count
                    count_str = f"{vec_count}/{total} loops vectorized" if total > 0 else "no loop counts available"
                    report_lines.extend([
                        "",
                        f"=== {cell} ===",
                        f"Return code: {rc}",
                        f"Vectorized: {status}",
                        f"Loop counts: {count_str} ({miss_count} not vectorized)",
                        "Reasons:",
                        *[f"- {r}" for r in reasons],
                        f"Artifacts: vec_reports/{sdfg_path.stem}/{cell}/",
                    ])

                    # ── Fortran baseline ──────────────────────────────────────
                    f90_path = bench_dir / f"{bench_name}.f90"
                    if f90_path.exists():
                        fort_out = bench_dir / "vec_reports" / "fortran" / bench_name / cell
                        frc, fstatus, freasons, fvec, fmiss = compile_fortran(
                            f90_path, fort_out, compiler, cost_model, env
                        )
                        ftotal = fvec + fmiss
                        fcount = f"{fvec}/{ftotal} loops vectorized" if ftotal > 0 else "no loop counts available"
                        report_lines.extend([
                            "",
                            f"--- Fortran baseline ({next(iter(_FORTRAN_COMPILER_CANDIDATES.get(compiler, ['?'])), '?')}) [{cell}] ---",
                            f"Return code: {frc}",
                            f"Vectorized: {fstatus}",
                            f"Loop counts: {fcount} ({fmiss} not vectorized)",
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())