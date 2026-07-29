#!/usr/bin/env python3
from __future__ import annotations

import argparse
import pathlib
import platform
import shutil
import statistics
import subprocess
import sys
from typing import Iterable

import numpy as np

_THIS_MODULE = pathlib.Path(__file__).stem  # 'only_timing_cloudsc_sdfg'

ALL_COMPILERS = ("clang", "gcc", "icpx")
ALL_COST_MODELS = ("default", "cheap", "unlimited", "disabled")
ALL_CPUS = (
    "amd_epyc", "amd_epyc_genoa", "apple_m_series",
    "arm_grace", "fugaku_a64fx", "ibm_power", "intel_xeon",
)

# ---------------------------------------------------------------------------
# Fortran compiler candidates, optimisation flags, and CloudSC symbol defaults
# ---------------------------------------------------------------------------

# Fortran compiler candidates per C++ compiler family (tried in order).
# flang-new is the real LLVM Fortran driver; bare `flang` is often a stub.
_FORTRAN_COMPILER_CANDIDATES = {
    "clang": ["flang-new", "flang"],
    "gcc":   ["gfortran"],
    "icpx":  ["ifx", "ifort"],
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

# Default values for unresolved CloudSC symbolic dimensions so make_inputs()
# can allocate arrays without crashing on dace.symbol objects.
_DEFAULT_SYMBOL_VALS = {
    "klon": 4194304, "klev": 6000, "nclv": 5,
    "ncldql": 1, "ncldqi": 2, "ncldqr": 3, "ncldqs": 4, "ncldqv": 5,
    "kidia": 1, "kfdia": 4194304,
}


def _resolve_dim(s) -> int:
    """Convert a DaCe shape dimension to a Python int, using CloudSC defaults
    for unresolved symbolic dimensions."""
    try:
        return int(s)
    except (TypeError, ValueError):
        return _DEFAULT_SYMBOL_VALS.get(str(s).lower(), 64)


# ---------------------------------------------------------------------------
# Reuse the same env-sourcing / build-env machinery as the vectorisation
# script so timing runs under *identical* compiler flags per cell.
# ---------------------------------------------------------------------------

_BASE_MODEL_CLANG = "-O3 -march=native -fno-math-errno -fno-trapping-math -fno-signed-zeros"
_BASE_MODEL_GCC = "-O3 -march=native -fno-math-errno -fno-trapping-math -fno-signed-zeros -fno-signaling-nans"
_BASE_MODEL_CLANG_DISABLED = "-O0 -march=native -fno-math-errno -fno-trapping-math -fno-signed-zeros"

_COST_MODEL_CXXFLAGS = {
    "disabled":  "-fno-vectorize -fno-slp-vectorize",
    "default":   "-fvectorize",
    "unlimited": "-Rpass-analysis=loop-vectorize",
}
_COST_MODEL_CXXFLAGS_GCC = {
    "disabled":  "-fno-tree-vectorize",
    "cheap":     "-ftree-vectorize -fvect-cost-model=cheap",
    "default":   "-ftree-vectorize -fvect-cost-model=dynamic",
    "unlimited": "-fno-vect-cost-model",
}


def _strip_mllvm_flags(flags_str: str) -> str:
    tokens = flags_str.split()
    out, skip_next = [], False
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
    import os
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

    if compiler == "gcc":
        base_and_opt = f"{_BASE_MODEL_GCC} {opt_flags}".strip()
    else:
        base_and_opt = (
            f"{_BASE_MODEL_CLANG_DISABLED} {opt_flags}".strip()
            if cost_model == "disabled"
            else f"{_BASE_MODEL_CLANG} {opt_flags}".strip()
        )

    existing = env.get("CXXFLAGS", "").strip()
    if base_and_opt:
        env["CXXFLAGS"] = f"{existing} {base_and_opt}".strip()
        env["DACE_compiler_cpu_args"] = f"{env.get('DACE_compiler_cpu_args', '')} {_strip_mllvm_flags(base_and_opt)}".strip()
    # Timing runs must NOT carry -Rpass/-fopt-info remark flags: they slow
    # compilation and clutter stderr, and we don't need them here.
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


# ---------------------------------------------------------------------------
# SDFG discovery — identical to the vectorisation script, so both scripts
# stay in lock-step on which kernels/variants exist.
# ---------------------------------------------------------------------------

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


def discovered_cells(vec_reports_dir: pathlib.Path) -> list[str]:
    """List the compiler_cpu_costmodel cell names already compiled under
    <sdfg_stem>/vec_reports/, so we time exactly what was vectorisation-tested."""
    if not vec_reports_dir.is_dir():
        return []
    return sorted(p.name for p in vec_reports_dir.iterdir() if p.is_dir())


def parse_cell(cell: str) -> tuple[str, str, str]:
    """cell = f'{compiler}_{cpu}_{cost_model}' -> (compiler, cpu, cost_model)."""
    for compiler in ALL_COMPILERS:
        if cell.startswith(compiler + "_"):
            rest = cell[len(compiler) + 1:]
            for cost_model in ALL_COST_MODELS:
                if rest.endswith("_" + cost_model):
                    cpu = rest[: -(len(cost_model) + 1)]
                    return compiler, cpu, cost_model
    raise ValueError(f"Cannot parse cell name: {cell}")


# ---------------------------------------------------------------------------
# Argument synthesis: build random-but-valid inputs for a compiled SDFG from
# its own arglist, so we can call it without hand-writing a harness per kernel.
# ---------------------------------------------------------------------------

def make_inputs(sdfg, seed: int = 0) -> dict:
    import dace
    rng = np.random.default_rng(seed)
    args = {}
    for name, desc in sdfg.arglist().items():
        if isinstance(desc, dace.data.Array):
            shape = tuple(_resolve_dim(s) for s in desc.shape)
            dtype = desc.dtype.as_numpy_dtype()
            if np.issubdtype(dtype, np.floating):
                arr = rng.random(shape).astype(dtype)
            elif np.issubdtype(dtype, np.integer):
                arr = rng.integers(1, 10, size=shape).astype(dtype)
            else:
                arr = np.zeros(shape, dtype=dtype)
            args[name] = arr
        elif isinstance(desc, dace.data.Scalar):
            dtype = desc.dtype.as_numpy_dtype()
            # NumPy >= 2.0 returns new-style DType classes (numpy.dtypes.Int32DType)
            # which are not directly callable as scalar constructors.  Always
            # go through np.dtype(...).type to get the proper scalar type.
            scalar_t = np.dtype(dtype).type
            if np.issubdtype(dtype, np.floating):
                args[name] = scalar_t(rng.random())
            elif np.issubdtype(dtype, np.integer):
                args[name] = scalar_t(4)
            else:
                args[name] = scalar_t(0)
        else:
            args[name] = None
    return args


# ---------------------------------------------------------------------------
# Timing core
# ---------------------------------------------------------------------------

def time_sdfg(
    sdfg_path: pathlib.Path,
    out_dir: pathlib.Path,
    env: dict,
    repeats: int,
    warmup: int,
) -> dict:
    """(Re)build the SDFG into out_dir/build and time `repeats` executions.

    Returns a dict with min/max/mean/median/stdev (seconds) or an 'error' key."""
    import os
    import dace

    out_dir.mkdir(parents=True, exist_ok=True)
    build_folder = out_dir / "build"
    build_folder.mkdir(parents=True, exist_ok=True)

    driver = out_dir / "timing_driver.py"
    # driver.write_text(
    # "import json, pathlib, sys\n"
    # "import numpy as np\n"
    # "import dace\n"
    # "sys.path.insert(0, r'" + str(pathlib.Path(__file__).resolve().parent) + "')\n"
    # f"from {_THIS_MODULE} import make_inputs\n"
    # "from timer_module import InstrumentWithTimer\n"
    # f"sdfg = dace.SDFG.from_file(r'{str(sdfg_path)}')\n"
    # "sdfg.build_folder = str(pathlib.Path(r'" + str(build_folder) + "'))\n"
    # "result_name = InstrumentWithTimer().apply_pass(sdfg, {})\n"
    # "csdfg = sdfg.compile()\n"
    # "args = make_inputs(sdfg)\n"
    # f"warmup = {warmup}\n"
    # f"repeats = {repeats}\n"
    # "args['time_ns'] = np.zeros(1, dtype=np.int64)\n"
    # "for _ in range(warmup):\n"
    # "    csdfg(**args)\n"
    # "times = []\n"
    # "for _ in range(repeats):\n"
    # "    csdfg(**args)\n"
    # "    print('checksum:', float(np.sum(args['zsnowaut'])), file=sys.stderr)\n"
    # "    times.append(int(args['time_ns'][0]))\n"
    # # "print(json.dumps(times))\n"
    # "print(times)\n"
    # )

    driver.write_text(
        "import json, pathlib, sys\n"
        "import numpy as np\n"
        "import dace\n"

        "import time\n"

        "sys.path.insert(0, r'" + str(pathlib.Path(__file__).resolve().parent) + "')\n"
        f"from {_THIS_MODULE} import make_inputs\n"
        "from timer_module import InstrumentWithTimer\n"
        f"sdfg = dace.SDFG.from_file(r'{str(sdfg_path)}')\n"
        "sdfg.build_folder = str(pathlib.Path(r'" + str(build_folder) + "'))\n"
        "result_name = InstrumentWithTimer().apply_pass(sdfg, {})\n"
        "csdfg = sdfg.compile()\n"
        "args = make_inputs(sdfg)\n"
        f"warmup = {warmup}\n"
        f"repeats = {repeats}\n"
        "args['time_ns'] = np.zeros(1, dtype=np.int64)\n"
        "for _ in range(warmup):\n"
        "    csdfg(**args)\n"
        "times = []\n"

        "t0 = time.perf_counter_ns()\n"

        "for _ in range(repeats):\n"
        "    csdfg(**args)\n"
        "    times.append(int(args['time_ns'][0]))\n"
        # "print(json.dumps(times))\n"

        "t1 = time.perf_counter_ns()\n"
        "total_ns = t1 - t0\n"
        "avg_ns_per_call = total_ns / repeats\n"
        "print(f'avg_ns_per_call: {avg_ns_per_call}', file=sys.stderr)\n"

        "print(times)\n"
    )

    proc = subprocess.run(
        [sys.executable, str(driver)],
        capture_output=True, text=True, env=env,
    )
    (out_dir / "timing_stdout.txt").write_text(proc.stdout)
    (out_dir / "timing_stderr.txt").write_text(proc.stderr)

    if proc.returncode != 0 or not proc.stdout.strip():
        return {"error": proc.stderr.strip()[-2000:] or "no output produced"}

    import json
    try:
        times = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as exc:  # noqa: BLE001
        return {"error": f"could not parse timing output: {exc}"}

    return {
        "runs": times,
        "min": min(times),
        "max": max(times),
        "mean": statistics.mean(times),
        "median": statistics.median(times),
        "stdev": statistics.stdev(times) if len(times) > 1 else 0.0,
    }


# def format_timing_block(cell: str, result: dict, label: str = "") -> list[str]:
#     #comes in as nanoseconds
#     header = f"=== {cell} ===" if not label else f"--- {label} [{cell}] ---"
#     lines = ["", header]
#     if "error" in result:
#         lines.append(f"ERROR: {result['error']}")
#         return lines
#     lines.extend([
#         f"Runs: {len(result['runs'])}",
#         f"Min:    {result['min'] / 1.0e3:.3f} us",
#         f"Median: {result['median'] / 1.0e3:.3f} us",
#         f"Mean:   {result['mean'] / 1.0e3:.3f} us",
#         f"Max:    {result['max'] / 1.0e3:.3f} us",
#         f"Stdev:  {result['stdev'] / 1.0e3:.3f} us",
#     ])
#     return lines


# def format_timing_block_sdfg(cell: str, result: dict, label: str = "") -> list[str]:
#     #comes in as nanoseconds
#     header = f"=== {cell} ===" if not label else f"--- {label} [{cell}] ---"
#     lines = ["", header]
#     if "error" in result:
#         lines.append(f"ERROR: {result['error']}")
#         return lines
#     lines.extend([
#         f"Runs: {len(result['runs'])}",
#         f"Min:    {result['min'] :.3f} us",
#         f"Median: {result['median'] :.3f} us",
#         f"Mean:   {result['mean'] :.3f} us",
#         f"Max:    {result['max'] :.3f} us",
#         f"Stdev:  {result['stdev'] :.3f} us",
#     ])
#     return lines

def format_timing_block(cell: str, result: dict, label: str = "") -> list[str]:
    #comes in as nanoseconds
    header = f"=== {cell} ===" if not label else f"--- {label} [{cell}] ---"
    lines = ["", header]
    if "error" in result:
        lines.append(f"ERROR: {result['error']}")
        return lines
    lines.extend([
        f"Runs: {len(result['runs'])}",
        f"Min:    {result['min']} ns",
        f"Median: {result['median']} ns",
        f"Mean:   {result['mean']} ns",
        f"Max:    {result['max']} ns",
        f"Stdev:  {result['stdev']} ns",
    ])
    return lines


def format_timing_block_sdfg(cell: str, result: dict, label: str = "") -> list[str]:
    #comes in as nanoseconds
    header = f"=== {cell} ===" if not label else f"--- {label} [{cell}] ---"
    lines = ["", header]
    if "error" in result:
        lines.append(f"ERROR: {result['error']}")
        return lines
    lines.extend([
        f"Runs: {len(result['runs'])}",
        f"Min:    {result['min']} ns",
        f"Median: {result['median']} ns",
        f"Mean:   {result['mean']} ns",
        f"Max:    {result['max']} ns",
        f"Stdev:  {result['stdev']} ns",
    ])
    return lines

# ---------------------------------------------------------------------------
# Fortran baseline timing via _w_timer.f90
# ---------------------------------------------------------------------------

def compile_fortran_timer_so(
    f90_w_timer: pathlib.Path,
    bench_name: str,
    out_dir: pathlib.Path,
    compiler: str,
    cost_model: str,
    env: dict,
) -> "pathlib.Path | None":
    """Compile <bench_name>_w_timer.f90 into a shared library for timing.

    The output is named lib<bench_name>_orig.so so that the kernel's
    run_<bench_name>.py harness will pick it up without modification."""
    fc = next(
        (c for c in _FORTRAN_COMPILER_CANDIDATES.get(compiler, []) if shutil.which(c)),
        None,
    )
    if not fc:
        return None

    so_path = out_dir / f"lib{bench_name}_orig.so"
    if so_path.exists():
        return so_path  # already compiled for this cell

    out_dir.mkdir(parents=True, exist_ok=True)
    opt = (_FORTRAN_OPT_FLAGS_GCC if compiler == "gcc" else _FORTRAN_OPT_FLAGS).get(
        cost_model, "-O3 -march=native"
    )
    cmd = [fc, *opt.split(), "-fPIC", "-shared", str(f90_w_timer), "-o", str(so_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    (out_dir / "fortran_compile_stdout.txt").write_text(proc.stdout)
    (out_dir / "fortran_compile_stderr.txt").write_text(proc.stderr)
    if proc.returncode != 0:
        return None
    return so_path


def time_fortran(
    bench_name: str,
    bench_dir: pathlib.Path,
    out_dir: pathlib.Path,
    compiler: str,
    cost_model: str,
    env: dict,
    repeats: int,
    warmup: int,
) -> dict:
    """Compile <bench_name>_w_timer.f90 with the right flags and time it by
    delegating to the kernel's own run_<bench_name>.py harness, which already
    has the correct ctypes argument layout.  Wall-clock time is measured with
    perf_counter around each call."""
    f90_timer = bench_dir / f"{bench_name}_w_timer.f90"
    if not f90_timer.exists():
        return {"error": f"_w_timer.f90 not found: {f90_timer}"}

    so_path = compile_fortran_timer_so(f90_timer, bench_name, out_dir, compiler, cost_model, env)
    if so_path is None:
        candidates = _FORTRAN_COMPILER_CANDIDATES.get(compiler, [])
        return {"error": f"Fortran compiler not available (tried: {', '.join(candidates)}) or compilation failed"}

    run_module = bench_dir / f"run_{bench_name}.py"
    if not run_module.exists():
        return {"error": f"run harness not found: {run_module}"}

    driver = out_dir / "fortran_timing_driver.py"
    driver.write_text(
        "import json, re, sys\n"
        "import numpy as np\n"
        f"sys.path.insert(0, r'{str(bench_dir)}')\n"
        f"import run_{bench_name} as mod\n"
        # Point the harness at our per-cell compiled .so.
        f"mod.HERE = r'{str(out_dir)}'\n"
        # Detect calling convention at runtime:
        #   autoconversion_snow: make_inputs() -> (consts, arrays),
        #                        run_original_fortran(consts, arrays)
        #   all others:          make_inputs() -> dict,
        #                        run_original_fortran(arrays)
        "import inspect as _inspect\n"
        "_result = mod.make_inputs()\n"
        "_nparams = len(_inspect.signature(mod.run_original_fortran).parameters)\n"
        "if _nparams >= 2:\n"
        "    _consts, _arrays = _result\n"
        "    def _call(): mod.run_original_fortran(_consts, _arrays)\n"
        "else:\n"
        "    _arrays = _result\n"
        "    def _call(): mod.run_original_fortran(_arrays)\n"
        f"warmup = {warmup}\n"
        f"repeats = {repeats}\n"
        "for _ in range(warmup):\n"
        "    _call()\n"
        # _w_timer.f90 uses system_clock internally and prints:
        #   " Elapsed time (seconds):  <val>"
        # on every call. Since this subprocess has capture_output=True,
        # all Fortran print* output lands in proc.stdout.
        "for _ in range(repeats):\n"
        "    _call()\n"
        "# Sentinel so the parent knows the runs finished\n"
        "print('__FORTRAN_DONE__')\n"
    )

    proc = subprocess.run(
        [sys.executable, str(driver)],
        capture_output=True, text=True, env=env,
    )
    (out_dir / "fortran_timing_stdout.txt").write_text(proc.stdout)
    (out_dir / "fortran_timing_stderr.txt").write_text(proc.stderr)

    if proc.returncode != 0 or "__FORTRAN_DONE__" not in proc.stdout:
        return {"error": proc.stderr.strip()[-2000:] or "no output produced"}

    # Parse the "Elapsed time (seconds): <val>" lines emitted by system_clock
    # inside _w_timer.f90.  Skip warmup lines (they appear first); take the
    # last `repeats` occurrences.
    import re
    elapsed_re = re.compile(r"Elapsed time \(nanoseconds\):\s*([\d.]+)")
    all_times = [float(m.group(1)) for m in elapsed_re.finditer(proc.stdout)]
    # Warmup calls also print — discard the leading warmup entries.
    times = all_times[-repeats:] if len(all_times) >= repeats else all_times
    if not times:
        return {"error": "no 'Elapsed time (seconds):' lines found in Fortran output"}

    return {
        "runs": times,
        "min": min(times),
        "max": max(times),
        "mean": statistics.mean(times),
        "median": statistics.median(times),
        "stdev": statistics.stdev(times) if len(times) > 1 else 0.0,
    }


def parse_args(argv: Iterable[str] | None = None):
    ap = argparse.ArgumentParser(description="Time CloudSC/TSVC SDFG kernel variants using existing vec_reports layout.")
    ap.add_argument("--root", default="cloudsc_variants", help="Root folder containing benchmark subfolders.")
    ap.add_argument("--compilers", nargs="+", default=None, choices=ALL_COMPILERS,
                     help="If omitted, times every compiler cell found under vec_reports/.")
    ap.add_argument("--cost-models", nargs="+", default=None, choices=ALL_COST_MODELS,
                     help="If omitted, times every cost-model cell found under vec_reports/.")
    ap.add_argument("--cpus", nargs="+", default=None, choices=ALL_CPUS,
                     help="If omitted, times every CPU cell found under vec_reports/.")
    ap.add_argument("--pattern", default="*.sdfg", help="Glob pattern for SDFG discovery. Default: *.sdfg")
    ap.add_argument("--repeats", type=int, default=10, help="Number of timed executions per variant.")
    ap.add_argument("--warmup", type=int, default=2, help="Number of untimed warm-up executions per variant.")
    ap.add_argument("--no-fortran", action="store_true",
                    help="Skip Fortran baseline timing (skips _w_timer.f90 compilation).")
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
        print(f"Bench name: [{bench_name}], bench dir:({bench_dir}) , path:{sdfg_path}\n")
        vec_reports_dir = bench_dir / "vec_reports" / sdfg_path.stem
        cells = discovered_cells(vec_reports_dir)
        if not cells:
            print(f"[{bench_name}] no vec_reports cells found, skipping (run the vectorisation script first)")
            continue

        report_lines = [f"Benchmark: {bench_name}", f"SDFG: {sdfg_path.name}",
                         f"Repeats: {args.repeats}  Warmup: {args.warmup}"]

        for cell in cells:
            compiler, cpu, cost_model = parse_cell(cell)
            if args.compilers and compiler not in args.compilers:
                continue
            if args.cost_models and cost_model not in args.cost_models:
                continue
            if args.cpus and cpu not in args.cpus:
                continue

            print(f"[{bench_name}] timing {cell} :: {sdfg_path.name}")
            script_path = ensure_env_script(cell, compiler, cost_model, cpu)
            env = _build_env(_source_env(script_path), compiler, cost_model)

            out_dir = vec_reports_dir / cell
            result = time_sdfg(sdfg_path, out_dir, env, args.repeats, args.warmup)

            # timing.txt next to this cell's summary.txt
            timing_lines = [f"Benchmark: {bench_name}", f"Cell: {cell}"]
            timing_lines.extend(format_timing_block_sdfg(cell, result))

            # ── Fortran baseline timing ──────────────────────────────────────
            if not args.no_fortran:
                fort_out = bench_dir / "vec_reports" / "fortran" / bench_name / cell
                fort_result = time_fortran(
                    bench_name, bench_dir, fort_out,
                    compiler, cost_model, env,
                    args.repeats, args.warmup,
                )
                fc_name = next(iter(_FORTRAN_COMPILER_CANDIDATES.get(compiler, ["?"])), "?")
                timing_lines.extend(format_timing_block(cell, fort_result, label=f"Fortran baseline ({fc_name})"))
                report_lines.extend(format_timing_block(cell, fort_result, label=f"Fortran baseline ({fc_name})"))
                report_lines.append(f"Artifacts: vec_reports/fortran/{bench_name}/{cell}/")

            (out_dir / "timing.txt").write_text("\n".join(timing_lines) + "\n")

            report_lines.extend(format_timing_block(cell, result))
            report_lines.append(f"Artifacts: vec_reports/{sdfg_path.stem}/{cell}/timing.txt")

        report_path = bench_dir / f"timing_report_{sdfg_path.stem}.txt"
        report_path.write_text("\n".join(report_lines) + "\n")
        print(f"Saved {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())