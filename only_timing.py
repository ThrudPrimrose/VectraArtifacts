#!/usr/bin/env python3
"""
only_timing.py — time pre-compiled CPP + DaCe TSVC kernels.

Expects kernels to have been compiled already by run_compile_sweep.py.
No recompilation is performed. Results are written as timing_report.csv
alongside the existing vec_report.txt in each cell directory.

Examples
--------
# Time the same cells that were compiled
python3 only_timing.py --compilers clang --cost-models unlimited --cpus apple_m_series

# All cost-models, both precisions, 200 reps
python3 only_timing.py \
    --compilers clang gcc \
    --cost-models default cheap unlimited disabled \
    --cpus apple_m_series \
    --precision both \
    --reps 200

# tsvc_2_5 layout
python3 only_timing.py \
    --tsvc-version tsvc_2_5 \
    --compilers clang \
    --cost-models unlimited \
    --cpus apple_m_series
"""

from __future__ import annotations

import argparse
import os
import pathlib
import platform
import statistics
import subprocess
import sys
import time as _time
from typing import Optional


# ── Valid choices ──────────────────────────────────────────────────────────────
ALL_COMPILERS   = ("clang", "gcc", "icpx")
ALL_COST_MODELS = ("default", "cheap", "unlimited", "disabled")
ALL_CPUS        = (
    "amd_epyc", "amd_epyc_genoa", "apple_m_series",
    "arm_grace", "fugaku_a64fx", "ibm_power", "intel_xeon",
)
ALL_PRECISIONS  = ("double", "float", "both")

TSVC_VERSION_CONFIG = {
    "tsvc_2": {
        "module":           "tsvc_2",
        "cpp_kernels_dir":  "tsvc_2/tsvc_cpp_microkernels",
        "dace_kernels_dir": "tsvc_2/tsvc_dace_microkernels",
    },
    "tsvc_2_5": {
        "module":           "tsvc_2_5",
        "cpp_kernels_dir":  "tsvc_2_5/tsvc_2_5_cpp_microkernels",
        "dace_kernels_dir": "tsvc_2_5/tsvc_2_5_dace_microkernels",
    },
}

_PRECISION_PATTERNS: dict = {
    ("double", "tsvc_2"):   ("*_d_single.cpp", "*_d_single.py"),
    ("float",  "tsvc_2"):   ("*_f_single.cpp", "*_f_single.py"),
    ("double", "tsvc_2_5"): ("*_d.cpp",        "*_d.py"),
    ("float",  "tsvc_2_5"): ("*_f.cpp",        "*_f.py"),
}

_COST_MODEL_CXXFLAGS = {
    "default":   "-O2",
    "cheap":     "-O1",
    "unlimited": "-O3 -ffast-math -march=native",
    "disabled":  "-O0 -fno-vectorize",
}
_COST_MODEL_CXXFLAGS_GCC = {
    "default":   "-O2",
    "cheap":     "-O1",
    "unlimited": "-O3 -ffast-math -march=native",
    "disabled":  "-O0 -fno-tree-vectorize",
}


# ── Helpers ────────────────────────────────────────────────────────────────────
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

    opt_flags = (
        _COST_MODEL_CXXFLAGS_GCC if compiler == "gcc" else _COST_MODEL_CXXFLAGS
    ).get(cost_model, "")
    if opt_flags:
        existing = env.get("CXXFLAGS", "")
        env["CXXFLAGS"] = f"{opt_flags} {existing}".strip()

    return env


def _read_vec_report(vec_report_path: pathlib.Path) -> dict[str, str]:
    """
    Parse vec_report.txt into {kernel_name: "VEC"|"---"}.
    Line format:  [VEC] kernel_name  (vec=N, missed=M)
    """
    result: dict[str, str] = {}
    if not vec_report_path.exists():
        return result
    for line in vec_report_path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("[VEC]") or line.startswith("[---]"):
            tag  = line[:5]
            rest = line[5:].strip().split()[0]          # kernel name is first token
            kernel = rest.rstrip("_").lstrip()
            result[kernel] = "VEC" if tag == "[VEC]" else "---"
    return result


CSV_HEADER = "kernel,median_us,min_us,max_us,stdev_us,reps,vectorized"


def _write_csv(out_path: pathlib.Path, rows: list[dict]) -> None:
    lines = [CSV_HEADER]
    for r in sorted(rows, key=lambda x: x["kernel"]):
        lines.append(
            f"{r['kernel']},"
            f"{r['median_us']:.2f},"
            f"{r['min_us']:.2f},"
            f"{r['max_us']:.2f},"
            f"{r['stdev_us']:.2f},"
            f"{r['reps']},"
            f"{r['vectorized']}"
        )
    out_path.write_text("\n".join(lines) + "\n")


# ── CPP timing ─────────────────────────────────────────────────────────────────
def _time_cpp_cell(
    cell_dir: pathlib.Path,
    tsvc_module: str,
    cpp_kernels: str,
    pattern: str,
    reps: int,
    len_1d: int,
    kernel_timeout: int,
    env: dict,
) -> pathlib.Path | None:
    """
    Invoke compile_cpp_kernels --time (no --force) against the pre-compiled
    build dir and write timing_report.csv into cell_dir.
    Returns the CSV path on success, None on failure.
    """
    build_dir  = cell_dir / "build"
    timing_out = cell_dir / "timing_report.csv"

    if not build_dir.exists():
        print(f"    [CPP] SKIP — build dir missing: {build_dir}", file=sys.stderr)
        return None

    cmd = [
        "python3", "-m", f"{tsvc_module}.compile_cpp_kernels",
        cpp_kernels,
        "-b",           str(build_dir),
        "--pattern",    pattern,
        "--time",
        "--reps",       str(reps),
        "--len-1d",     str(len_1d),
        "--timing-out", str(timing_out),
        # no --force: reuse the pre-compiled .so
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    (cell_dir / "timing_stdout.txt").write_text(result.stdout)
    (cell_dir / "timing_stderr.txt").write_text(result.stderr)

    if result.returncode != 0:
        print(f"    [CPP] FAILED — see {cell_dir}/timing_stderr.txt", file=sys.stderr)
        return None

    return timing_out


# ── DaCe timing ────────────────────────────────────────────────────────────────
def _time_dace_cell(
    cell_dir: pathlib.Path,
    tsvc_module: str,
    dace_kernels: str,
    pattern: str,
    reps: int,
    len_1d: int,
    kernel_timeout: int,
    env: dict,
) -> pathlib.Path | None:
    """
    Invoke compile_dace_kernels --time (no --force) against the pre-compiled
    build dir and write timing_report.csv into cell_dir.
    Returns the CSV path on success, None on failure.
    """
    build_dir  = cell_dir / "build"
    timing_out = cell_dir / "timing_report.csv"

    if not build_dir.exists():
        print(f"    [DaCe] SKIP — build dir missing: {build_dir}", file=sys.stderr)
        return None

    cmd = [
        "python3", "-m", f"{tsvc_module}.compile_dace_kernels",
        dace_kernels,
        "-b",              str(build_dir),
        "--pattern",       pattern,
        "--time",
        "--reps",          str(reps),
        "--len-1d",        str(len_1d),
        "--timing-out",    str(timing_out),
        "--kernel-timeout", str(kernel_timeout),
        # no --force: reuse the pre-compiled .sdfgz + .so
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    (cell_dir / "timing_stdout.txt").write_text(result.stdout)
    (cell_dir / "timing_stderr.txt").write_text(result.stderr)

    if result.returncode != 0:
        print(f"    [DaCe] FAILED — see {cell_dir}/timing_stderr.txt", file=sys.stderr)
        return None

    return timing_out


# ── CLI ────────────────────────────────────────────────────────────────────────
def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Time pre-compiled CPP + DaCe TSVC kernels (no recompilation).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Must be run after run_compile_sweep.py with matching arguments.

valid compilers   : {", ".join(ALL_COMPILERS)}
valid cost-models : {", ".join(ALL_COST_MODELS)}
valid cpus        : {", ".join(ALL_CPUS)}
valid versions    : {", ".join(TSVC_VERSION_CONFIG)}
valid precisions  : {", ".join(ALL_PRECISIONS)}
        """,
    )
    ap.add_argument(
        "--compilers", nargs="+", default=["clang"], choices=ALL_COMPILERS,
        metavar="COMPILER",
        help=f"Compilers to sweep. (default: clang)",
    )
    ap.add_argument(
        "--cost-models", nargs="+", default=["unlimited"], choices=ALL_COST_MODELS,
        metavar="MODEL",
        help=f"Cost models to sweep. (default: unlimited)",
    )
    ap.add_argument(
        "--cpus", nargs="+", default=["apple_m_series"], choices=ALL_CPUS,
        metavar="CPU",
        help=f"CPU targets to sweep. (default: apple_m_series)",
    )
    ap.add_argument(
        "--precision", default="double", choices=ALL_PRECISIONS,
        help="Precision variant(s). 'both' times double then float. (default: double)",
    )
    ap.add_argument(
        "--tsvc-version", default="tsvc_2", choices=list(TSVC_VERSION_CONFIG),
        metavar="VERSION",
        help=f"TSVC version layout. (default: tsvc_2)",
    )
    ap.add_argument("--cpp-kernels",  default=None, metavar="DIR",
                    help="Override C++ microkernels source directory.")
    ap.add_argument("--dace-kernels", default=None, metavar="DIR",
                    help="Override DaCe microkernels source directory.")
    ap.add_argument("--results-cpp",  default=None, metavar="DIR",
                    help="Root results dir for C++ (default: results_cpp/<version>).")
    ap.add_argument("--results-dace", default=None, metavar="DIR",
                    help="Root results dir for DaCe (default: results_dace/<version>).")
    ap.add_argument("--reps", type=int, default=100, metavar="N",
                    help="Timing repetitions per kernel (default: 100).")
    ap.add_argument("--len-1d", type=int, default=1024, metavar="N", dest="len_1d",
                    help="Array length for timing (default: 1024).")
    ap.add_argument("--kernel-timeout", type=int, default=120, metavar="SEC",
                    dest="kernel_timeout",
                    help="Per-kernel timeout in seconds for DaCe (default: 120).")
    ap.add_argument("--no-cpp",  action="store_true", help="Skip CPP timing.")
    ap.add_argument("--no-dace", action="store_true", help="Skip DaCe timing.")
    return ap.parse_args(argv)


# ── Main ───────────────────────────────────────────────────────────────────────
def main(argv=None):
    args = parse_args(argv)

    vcfg         = TSVC_VERSION_CONFIG[args.tsvc_version]
    tsvc_module  = vcfg["module"]
    cpp_kernels  = args.cpp_kernels  or vcfg["cpp_kernels_dir"]
    dace_kernels = args.dace_kernels or vcfg["dace_kernels_dir"]

    base_cpp  = pathlib.Path(args.results_cpp  or f"results_cpp/{args.tsvc_version}")
    base_dace = pathlib.Path(args.results_dace or f"results_dace/{args.tsvc_version}")

    precisions = ["double", "float"] if args.precision == "both" else [args.precision]

    cells = [
        (f"{compiler}_{cpu}_{cost_model}", compiler, cost_model, cpu)
        for compiler   in args.compilers
        for cost_model in args.cost_models
        for cpu        in args.cpus
    ]

    total = len(cells) * len(precisions)

    print(f"TSVC version  : {args.tsvc_version}  (module: {tsvc_module})")
    print(f"Results CPP   : {base_cpp}")
    print(f"Results DaCe  : {base_dace}")
    print(f"Compilers     : {args.compilers}")
    print(f"Cost models   : {args.cost_models}")
    print(f"CPUs          : {args.cpus}")
    print(f"Precisions    : {precisions}")
    print(f"Reps          : {args.reps}  |  len_1d={args.len_1d}  |  kernel_timeout={args.kernel_timeout}s")
    print(f"Cells         : {total}")
    print(f"Skip CPP      : {args.no_cpp}  |  Skip DaCe: {args.no_dace}")

    scripts_dir = pathlib.Path("scripts")
    idx = 0

    for precision in precisions:
        key = (precision, args.tsvc_version)
        if key not in _PRECISION_PATTERNS:
            print(f"WARNING: no pattern for {key}, skipping precision={precision}", file=sys.stderr)
            continue
        pattern_cpp, pattern_dace = _PRECISION_PATTERNS[key]

        for name, compiler, cost_model, cpu in cells:
            idx += 1
            print(f"\n=== [{idx}/{total}] [{precision}] {name} ===")

            # Source environment (script must exist from compile step)
            script_path = scripts_dir / f"source.{name}.sh"
            if not script_path.exists():
                # Regenerate if missing (e.g. scripts/ was cleaned)
                subprocess.run([
                    "vectra-source-sh",
                    "--compiler",   compiler,
                    "--cost-model", cost_model,
                    "--cpu",        cpu,
                    "--out",        str(script_path),
                ], check=True)

            env = _build_env(_source_env(script_path), compiler, cost_model)

            # ── CPP ───────────────────────────────────────────────────────────
            if not args.no_cpp:
                cpp_cell = base_cpp / precision / name
                if not cpp_cell.exists():
                    print(f"  CPP  SKIP — cell dir not found: {cpp_cell}")
                else:
                    t0  = _time.perf_counter()
                    out = _time_cpp_cell(
                        cell_dir=cpp_cell,
                        tsvc_module=tsvc_module,
                        cpp_kernels=cpp_kernels,
                        pattern=pattern_cpp,
                        reps=args.reps,
                        len_1d=args.len_1d,
                        kernel_timeout=args.kernel_timeout,
                        env=env,
                    )
                    elapsed = _time.perf_counter() - t0
                    if out:
                        print(f"  CPP  OK   ({elapsed:.1f}s) — {out}")
                    else:
                        print(f"  CPP  FAILED ({elapsed:.1f}s)")

            # ── DaCe ──────────────────────────────────────────────────────────
            if not args.no_dace:
                dace_cell = base_dace / precision / name
                if not dace_cell.exists():
                    print(f"  DaCe SKIP — cell dir not found: {dace_cell}")
                else:
                    t0  = _time.perf_counter()
                    out = _time_dace_cell(
                        cell_dir=dace_cell,
                        tsvc_module=tsvc_module,
                        dace_kernels=dace_kernels,
                        pattern=pattern_dace,
                        reps=args.reps,
                        len_1d=args.len_1d,
                        kernel_timeout=args.kernel_timeout,
                        env=env,
                    )
                    elapsed = _time.perf_counter() - t0
                    if out:
                        print(f"  DaCe OK   ({elapsed:.1f}s) — {out}")
                    else:
                        print(f"  DaCe FAILED ({elapsed:.1f}s)")

    print(f"\nDone. {idx} cell(s) timed.")


if __name__ == "__main__":
    main()