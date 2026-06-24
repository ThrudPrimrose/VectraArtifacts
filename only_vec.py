#!/usr/bin/env python3
"""
only_vec.py — compile CPP + DaCe TSVC kernels for one or more
compiler / cost-model / CPU combinations and generate vectorisation reports.

Timing is intentionally separated — run run_timing_sweep.py after this.

Examples
--------
# Single cell (equivalent to the hardcoded original)
python3 only_vec.py --compilers clang --cost-models unlimited --cpus apple_m_series

# Multiple compilers, all cost-models, double + float
python3 only_vec.py --compilers clang gcc --cost-models default cheap unlimited disabled --cpus apple_m_series --precision both

# tsvc_2_5 layout
python3 only_vec.py --tsvc-version tsvc_2_5 --compilers clang --cost-models unlimited --cpus apple_m_series
"""

from __future__ import annotations

import argparse
import os
import pathlib
import platform
import subprocess
import sys


# ── Valid choices ──────────────────────────────────────────────────────────────
ALL_COMPILERS   = ("clang", "gcc", "icpx")
ALL_COST_MODELS = ("default", "cheap", "unlimited", "disabled")
ALL_CPUS        = (
    "amd_epyc", "amd_epyc_genoa", "apple_m_series",
    "arm_grace", "fugaku_a64fx", "ibm_power", "intel_xeon",
)
ALL_PRECISIONS  = ("double", "float", "both")

# ── Per-version config ─────────────────────────────────────────────────────────
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

# ── Precision glob patterns ────────────────────────────────────────────────────
_PRECISION_PATTERNS: dict = {
    ("double", "tsvc_2"):   ("*_d_single.cpp", "*_d_single.py"),
    ("float",  "tsvc_2"):   ("*_f_single.cpp", "*_f_single.py"),
    ("double", "tsvc_2_5"): ("*_d.cpp",        "*_d.py"),
    ("float",  "tsvc_2_5"): ("*_f.cpp",        "*_f.py"),
}

# ── Cost-model optimisation flags ─────────────────────────────────────────────
# Injected into CXXFLAGS so compile_dace.py's _extra_flags_from_env() forwards
# them when regenerating per-kernel .rpt files.
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

# ── Vectorisation remark flags ─────────────────────────────────────────────────
_VEC_REMARK_FLAGS = {
    "clang": "-Rpass=loop-vectorize -Rpass-missed=loop-vectorize -Rpass-analysis=loop-vectorize",
    "gcc":   "-fopt-info-vec-optimized -fopt-info-vec-missed",
    "icpx":  "-Rpass=loop-vectorize -Rpass-missed=loop-vectorize -qopt-report=5 -qopt-report-phase=vec",
}


# ── Helpers ────────────────────────────────────────────────────────────────────
def _source_env(script_path: pathlib.Path) -> dict:
    """Source a shell script and return its exported environment as a dict."""
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
    """Apply macOS overrides, cost-model flags, and remark flags to env."""
    env = dict(env)

    # macOS compiler overrides
    if platform.system() == "Darwin":
        if compiler == "clang":
            env["CXX"] = "clang++"
            env["CXX_COMPILER"] = "clang"
            env["DACE_compiler_cpu_executable"] = "clang++"
        elif compiler == "gcc":
            env["CXX"] = "/opt/homebrew/bin/g++-15"
            env["CXX_COMPILER"] = "gcc"
            env["DACE_compiler_cpu_executable"] = "/opt/homebrew/bin/g++-15"

    # Cost-model optimisation flags (must come before remark flags in CXXFLAGS)
    opt_flags = (
        _COST_MODEL_CXXFLAGS_GCC if compiler == "gcc" else _COST_MODEL_CXXFLAGS
    ).get(cost_model, "")
    if opt_flags:
        existing = env.get("CXXFLAGS", "")
        env["CXXFLAGS"] = f"{opt_flags} {existing}".strip()

    # Vectorisation remark flags (diagnostic only — appended last)
    remark_flags = _VEC_REMARK_FLAGS.get(compiler, "")
    if remark_flags:
        env["CXXFLAGS"] = f"{env.get('CXXFLAGS', '')} {remark_flags}".strip()
        env["DACE_compiler_cpu_args"] = (
            f"{env.get('DACE_compiler_cpu_args', '')} {remark_flags}".strip()
        )

    return env


# ── CLI ────────────────────────────────────────────────────────────────────────
def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Compile CPP + DaCe TSVC kernels and generate vectorisation reports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
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
        help=f"One or more compilers. Choices: {', '.join(ALL_COMPILERS)}. (default: clang)",
    )
    ap.add_argument(
        "--cost-models", nargs="+", default=["default"], choices=ALL_COST_MODELS,
        metavar="MODEL",
        help=f"One or more cost-models. Choices: {', '.join(ALL_COST_MODELS)}. (default: unlimited)",
    )
    ap.add_argument(
        "--cpus", nargs="+", default=["apple_m_series"], choices=ALL_CPUS,
        metavar="CPU",
        help=f"One or more CPU targets. Choices: {', '.join(ALL_CPUS)}. (default: apple_m_series)",
    )
    ap.add_argument(
        "--precision", default="double", choices=ALL_PRECISIONS,
        help="Precision variant(s) to compile. 'both' runs double then float. (default: double)",
    )
    ap.add_argument(
        "--tsvc-version", default="tsvc_2", choices=list(TSVC_VERSION_CONFIG),
        metavar="VERSION",
        help=f"TSVC version layout. Choices: {', '.join(TSVC_VERSION_CONFIG)}. (default: tsvc_2)",
    )
    ap.add_argument("--cpp-kernels",  default=None, metavar="DIR",
                    help="Override C++ microkernels directory.")
    ap.add_argument("--dace-kernels", default=None, metavar="DIR",
                    help="Override DaCe microkernels directory.")
    ap.add_argument("--out-cpp",  default=None, metavar="DIR",
                    help="Root output dir for C++ results (default: results_cpp/<version>).")
    ap.add_argument("--out-dace", default=None, metavar="DIR",
                    help="Root output dir for DaCe results (default: results_dace/<version>).")
    ap.add_argument("-j", "--jobs", default=6, type=int, metavar="N",
                    help="Parallel compile jobs (default: 6).")
    ap.add_argument("--no-cpp",  action="store_true", help="Skip C++ compilation.")
    ap.add_argument("--no-dace", action="store_true", help="Skip DaCe compilation.")
    return ap.parse_args(argv)


# ── Core ───────────────────────────────────────────────────────────────────────
def compile_cell(
    name: str,
    compiler: str,
    cost_model: str,
    cpu: str,
    precision: str,
    tsvc_version: str,
    tsvc_module: str,
    cpp_kernels: str,
    dace_kernels: str,
    base_cpp: pathlib.Path,
    base_dace: pathlib.Path,
    jobs: int,
    skip_cpp: bool,
    skip_dace: bool,
) -> None:
    scripts_dir = pathlib.Path("scripts")
    scripts_dir.mkdir(exist_ok=True)
    script_path = scripts_dir / f"source.{name}.sh"

    # Generate the environment script if it doesn't exist yet
    if not script_path.exists():
        subprocess.run([
            "vectra-source-sh",
            "--compiler",   compiler,
            "--cost-model", cost_model,
            "--cpu",        cpu,
            "--out",        str(script_path),
        ], check=True)

    env = _build_env(_source_env(script_path), compiler, cost_model)

    key = (precision, tsvc_version)
    if key not in _PRECISION_PATTERNS:
        raise KeyError(f"No glob pattern for precision={precision!r}, tsvc_version={tsvc_version!r}")
    pattern_cpp, pattern_dace = _PRECISION_PATTERNS[key]

    # ── CPP ───────────────────────────────────────────────────────────────────
    if not skip_cpp:
        cpp_out_dir   = base_cpp / precision / name
        cpp_build_dir = cpp_out_dir / "build"
        cpp_out_dir.mkdir(parents=True, exist_ok=True)
        cpp_build_dir.mkdir(parents=True, exist_ok=True)

        result = subprocess.run([
            "python3", "-m", f"{tsvc_module}.compile_cpp_kernels",
            cpp_kernels,
            "-b",              str(cpp_build_dir),
            "--pattern",       pattern_cpp,
            "--vec-report",
            "--vec-report-out", str(cpp_out_dir / "vec_report.txt"),
            "--force",
            f"-j{jobs}",
        ], capture_output=True, text=True, env=env)

        (cpp_out_dir / "stdout.txt").write_text(result.stdout)
        (cpp_out_dir / "stderr.txt").write_text(result.stderr)
        status = "OK" if result.returncode == 0 else "FAILED"
        print(f"  CPP  {status} — {cpp_out_dir}/")
        if result.returncode != 0:
            print(result.stderr[-2000:], file=sys.stderr)

    # ── DaCe ──────────────────────────────────────────────────────────────────
    if not skip_dace:
        dace_out_dir   = base_dace / precision / name
        dace_build_dir = dace_out_dir / "build"
        dace_out_dir.mkdir(parents=True, exist_ok=True)
        dace_build_dir.mkdir(parents=True, exist_ok=True)

        result = subprocess.run([
            "python3", "-m", f"{tsvc_module}.compile_dace_kernels",
            dace_kernels,
            "-b",              str(dace_build_dir),
            "--pattern",       pattern_dace,
            "--vec-report",
            "--vec-report-out", str(dace_out_dir / "vec_report.txt"),
            "--force",
            f"-j{jobs}",
        ], capture_output=True, text=True, env=env)

        (dace_out_dir / "stdout.txt").write_text(result.stdout)
        (dace_out_dir / "stderr.txt").write_text(result.stderr)
        status = "OK" if result.returncode == 0 else "FAILED"
        print(f"  DaCe {status} — {dace_out_dir}/")
        if result.returncode != 0:
            print(result.stderr[-2000:], file=sys.stderr)


def main(argv=None):
    args = parse_args(argv)

    vcfg         = TSVC_VERSION_CONFIG[args.tsvc_version]
    tsvc_module  = vcfg["module"]
    cpp_kernels  = args.cpp_kernels  or vcfg["cpp_kernels_dir"]
    dace_kernels = args.dace_kernels or vcfg["dace_kernels_dir"]

    base_cpp  = pathlib.Path(args.out_cpp  or f"results_cpp/{args.tsvc_version}")
    base_dace = pathlib.Path(args.out_dace or f"results_dace/{args.tsvc_version}")

    precisions = ["double", "float"] if args.precision == "both" else [args.precision]

    # Build the list of cells up front so we can print a summary
    cells = [
        (f"{compiler}_{cpu}_{cost_model}", compiler, cost_model, cpu)
        for compiler   in args.compilers
        for cost_model in args.cost_models
        for cpu        in args.cpus
    ]

    print(f"TSVC version : {args.tsvc_version}  (module: {tsvc_module})")
    print(f"CPP kernels  : {cpp_kernels}")
    print(f"DaCe kernels : {dace_kernels}")
    print(f"Compilers    : {args.compilers}")
    print(f"Cost models  : {args.cost_models}")
    print(f"CPUs         : {args.cpus}")
    print(f"Precisions   : {precisions}")
    print(f"Cells        : {len(cells)} x {len(precisions)} precision(s) = {len(cells)*len(precisions)} runs")
    print(f"Skip CPP     : {args.no_cpp}")
    print(f"Skip DaCe    : {args.no_dace}")

    total = len(cells) * len(precisions)
    idx   = 0
    for precision in precisions:
        for name, compiler, cost_model, cpu in cells:
            idx += 1
            print(f"\n=== [{idx}/{total}] [{precision}] {name} ===")
            compile_cell(
                name=name,
                compiler=compiler,
                cost_model=cost_model,
                cpu=cpu,
                precision=precision,
                tsvc_version=args.tsvc_version,
                tsvc_module=tsvc_module,
                cpp_kernels=cpp_kernels,
                dace_kernels=dace_kernels,
                base_cpp=base_cpp,
                base_dace=base_dace,
                jobs=args.jobs,
                skip_cpp=args.no_cpp,
                skip_dace=args.no_dace,
            )

    print(f"\nDone. {idx} cell(s) compiled.")


if __name__ == "__main__":
    main()