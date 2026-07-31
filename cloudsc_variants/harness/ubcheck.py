"""Undefined-behaviour lane for the CloudSC variants: check the native code instead of timing it.

Three checkers over the same two lanes ``bench_variants.py`` compiles:

  clang-tidy       reads the DaCe-generated C++ (clang-analyzer + bugprone).
  gcc -fanalyzer   reads the same C++. ``-O0`` is load-bearing: GCC 15 emits nothing from
                   ``-fanalyzer`` at any optimisation level, so an ``-O2`` analyzer run is
                   silently useless.
  ASan + UBSan     rebuilds BOTH lanes instrumented -- the DaCe .so via ``DACE_compiler_cpu_args``
                   and the reference Fortran .so via gfortran -- and re-runs the benchmark under
                   ``LD_PRELOAD=libasan.so``. The preload is mandatory, not belt-and-braces: the
                   SDFG .so is dlopen'ed by CPython, so without it ASan is not first in the
                   initial library list and refuses to start rather than checking anything.

Every checker is armed against ``PROBE_SRC``, a deliberate heap overflow, before any real source
is looked at. A checker that stays quiet on the probe aborts the run -- a clean verdict from a
checker that was never running is worse than no verdict.

The sanitizer build drops ``-ffast-math``, which production keeps. UBSan's float checks are
meaningless under fast-math; ASan's heap checks are unaffected either way. Timing numbers from
this mode are therefore not comparable to a normal run and are not reported.
"""
import os
import shutil
import subprocess
import sys

import regen_sdfgs

BUILD_ROOT = os.path.join(os.path.expanduser("~"), ".cache", "cloudsc_ub")
# dace/codegen/CMakeLists.txt sets DACE_CPP_STANDARD to 20; the runtime headers need it.
CPP_STD = "-std=c++20"
# Reserved identifiers and swappable parameters are how DaCe codegen is written, not a finding.
TIDY_CHECKS = ("-*,clang-analyzer-*,bugprone-*,-bugprone-reserved-identifier,"
               "-bugprone-easily-swappable-parameters")
ANALYZER = ["g++", "-c", "-o", "/dev/null", "-fanalyzer", CPP_STD, "-O0"]

SAN = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g"]
SAN_CXX_ARGS = " ".join(
    ["-fPIC", "-Wall", "-Wextra", "-O2", "-march=native", "-Wno-unused-parameter", "-Wno-unused-label"] + SAN)
SAN_FORTRAN = ["gfortran", "-O2", "-march=native", "-fPIC", "-shared", "-fno-math-errno"] + SAN
# CPython and numpy leak by design at exit, and several .so carry the same DaCe runtime symbols.
ASAN_OPTIONS = "detect_leaks=0:detect_odr_violation=0:halt_on_error=1:print_stacktrace=1"
PROBE_CALL = "import ctypes, sys; ctypes.CDLL(sys.argv[1]).poke()"

PROBE_SRC = """#include <cstdlib>
// Deliberate heap overflow -- every checker must report this, or a clean verdict is worthless.
extern "C" void poke(void) {
    int *p = (int *)malloc(4 * sizeof(int));
    p[8] = 1;
    free(p);
}
"""


def diagnostics(text):
    """The compiler-style warning/error lines of a checker's output, without the code excerpts."""
    return [line for line in text.splitlines() if ": warning:" in line or ": error:" in line]


def findings(text):
    """Number of compiler-style warning/error lines in a checker's output."""
    return len(diagnostics(text))


def clang_tidy(source, includes):
    """(count, output) from clang-tidy over one translation unit."""
    cmd = ["clang-tidy", "--quiet", f"-checks={TIDY_CHECKS}", source, "--", CPP_STD]
    res = subprocess.run(cmd + [f"-I{d}" for d in includes], capture_output=True, text=True)
    out = res.stdout + res.stderr
    return findings(out), out


def gcc_analyzer(source, includes):
    """(count, output) from gcc -fanalyzer over one translation unit."""
    res = subprocess.run(ANALYZER + [f"-I{d}" for d in includes] + [source], capture_output=True, text=True)
    out = res.stdout + res.stderr
    return findings(out), out


def emit_sources(variant, frontends):
    """Write the DaCe C++ for each frontend without building it. Returns {frontend: (cpp, include_dirs)}."""
    import dace
    from dace.codegen import codegen, compiler

    runtime = os.path.join(os.path.dirname(os.path.abspath(dace.__file__)), "runtime", "include")
    out = {}
    for frontend in frontends:
        sdfg = dace.SDFG.from_file(regen_sdfgs.sdfg_path(variant, frontend))
        folder = os.path.join(BUILD_ROOT, "src", sdfg.name)
        compiler.generate_program_folder(sdfg, codegen.generate_code(sdfg), folder)
        cpp = os.path.join(folder, "src", "cpu", f"{sdfg.name}.cpp")
        out[frontend] = (cpp, [runtime, os.path.join(folder, "include")])
    return out


def probe_path():
    """Write the deliberate-overflow source the arming check runs every checker against."""
    path = os.path.join(BUILD_ROOT, "probe", "probe.cpp")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(PROBE_SRC)
    return path


def sanitizer_env():
    """Child environment that arms ASan for a CPython process which dlopens instrumented .so files."""
    libasan = subprocess.run(["gcc", "-print-file-name=libasan.so"], capture_output=True, text=True,
                             check=True).stdout.strip()
    return dict(os.environ,
                LD_PRELOAD=libasan,
                ASAN_OPTIONS=ASAN_OPTIONS,
                UBSAN_OPTIONS="print_stacktrace=1",
                DACE_compiler_cpu_args=SAN_CXX_ARGS,
                DACE_compiler_use_cache="0",
                DACE_default_build_folder=os.path.join(BUILD_ROOT, "asan"))


def arm(env):
    """Prove all three checkers report a known heap overflow before any real source is judged."""
    probe = probe_path()
    n_tidy, _ = clang_tidy(probe, [])
    n_gcc, _ = gcc_analyzer(probe, [])
    so = os.path.join(BUILD_ROOT, "probe", "libprobe.so")
    subprocess.run(["g++", "-shared", "-fPIC", "-O0", "-g", "-fsanitize=address", probe, "-o", so],
                   check=True,
                   capture_output=True,
                   text=True)
    res = subprocess.run([sys.executable, "-c", PROBE_CALL, so], capture_output=True, text=True, env=env)
    asan_fired = "AddressSanitizer" in res.stdout + res.stderr
    print(f"  arming probe: clang-tidy {n_tidy} finding(s), gcc -fanalyzer {n_gcc} finding(s), "
          f"ASan {'fired' if asan_fired else 'SILENT'}")
    if n_tidy == 0 or n_gcc == 0 or not asan_fired:
        raise AssertionError("a checker stayed quiet on a deliberate heap overflow -- its verdict means nothing")


def instrument_fortran(here, variant):
    """Rebuild the reference lane's .so with sanitizers; run_<variant>.py reuses whatever sits at this path."""
    so = os.path.join(here, variant, f"lib{variant}_orig.so")
    saved = os.path.join(BUILD_ROOT, "saved", f"lib{variant}_orig.so")
    os.makedirs(os.path.dirname(saved), exist_ok=True)
    if os.path.exists(so):
        shutil.move(so, saved)
    src = os.path.join(here, variant, f"{variant}_w_timer.f90")
    subprocess.run(SAN_FORTRAN + [src, "-o", so], check=True, capture_output=True, text=True)
    return so, saved


def restore_fortran(so, saved):
    """Put the uninstrumented .so back so the next timing run is not silently sanitized."""
    os.remove(so)
    if os.path.exists(saved):
        shutil.move(saved, so)


def sanitizer_run(here, variant, frontends, reps, env):
    """Re-run the plain benchmark for one variant with both lanes instrumented."""
    so, saved = instrument_fortran(here, variant)
    cmd = [
        sys.executable,
        os.path.join(here, "bench_variants.py"), "--only", variant, "--reps",
        str(reps), "--frontend", "both" if len(frontends) == 2 else frontends[0], "--skip-regen"
    ]
    res = subprocess.run(cmd, cwd=here, capture_output=True, text=True, env=env)
    restore_fortran(so, saved)
    out = res.stdout + res.stderr
    reports = [line for line in out.splitlines() if "ERROR: AddressSanitizer" in line or "runtime error:" in line]
    return res.returncode, reports, out


def show(label, count, output, limit=12):
    """Print one checker's verdict, and its diagnostics when it found something."""
    print(f"  [{label}] {count} finding(s)")
    lines = diagnostics(output)
    for line in lines[:limit]:
        print("      " + line)
    if len(lines) > limit:
        print(f"      ... {len(lines) - limit} more diagnostic(s)")


def check(here, variant, frontends, reps, env):
    """Run all three checkers over one variant. Returns True when every one came back clean."""
    print(f"\n=== UB CHECK: {variant} ===")
    clean = True
    for frontend, (cpp, includes) in emit_sources(variant, frontends).items():
        n, out = clang_tidy(cpp, includes)
        show(f"clang-tidy {frontend}", n, out)
        clean = clean and n == 0
        n, out = gcc_analyzer(cpp, includes)
        show(f"gcc -fanalyzer {frontend}", n, out)
        clean = clean and n == 0

    rc, reports, out = sanitizer_run(here, variant, frontends, reps, env)
    print(f"  [asan+ubsan] exit {rc}, {len(reports)} sanitizer report(s)")
    if reports or rc != 0:
        for line in out.splitlines()[-120:]:
            print("      " + line)
    return clean and rc == 0 and not reports


def run(here, variants, frontends, reps, regen):
    """Entry point for ``bench_variants.py --check-ub``. Returns a process exit code."""
    os.makedirs(BUILD_ROOT, exist_ok=True)
    env = sanitizer_env()
    print(f"UB check: build root {BUILD_ROOT}; sanitizer C++ flags {SAN_CXX_ARGS}")
    arm(env)

    verdicts = []
    for variant in variants:
        if regen:
            for frontend in frontends:
                regen_sdfgs.regen(variant, frontend)
        verdicts.append((variant, check(here, variant, frontends, reps, env)))

    print("\n" + "=" * 60)
    for variant, ok in verdicts:
        print(f"{variant:<40}{'CLEAN' if ok else 'FINDINGS'}")
    print("=" * 60)
    return 0 if all(ok for _, ok in verdicts) else 1
