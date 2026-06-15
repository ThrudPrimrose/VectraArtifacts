import subprocess
import pathlib
import os
import platform
import argparse


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


# ── Precision patterns per (precision, tsvc_version) ──────────────────────────
# Keys are (precision, version) tuples — NOT adjacent string literals which
# Python silently concatenates into one string at parse time.
_PRECISION_PATTERNS: dict = {
    ("double", "tsvc_2"):   ("*_d_single.cpp", "*_d_single.py"),
    ("float",  "tsvc_2"):   ("*_f_single.cpp", "*_f_single.py"),
    ("double", "tsvc_2_5"): ("*_d.cpp",        "*_d.py"),
    ("float",  "tsvc_2_5"): ("*_f.cpp",        "*_f.py"),
}


# ── CLI arguments ──────────────────────────────────────────────────────────────
def parse_args():
    ap = argparse.ArgumentParser(
        description="Run CPP + DaCe vectorization sweep across compiler/cost-model/CPU permutations.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
examples:
  # defaults: clang / all cost models / apple_m_series / tsvc_2 / double
  python3 run_sweep.py

  # use tsvc_2_5 kernel layout
  python3 run_sweep.py --tsvc-version tsvc_2_5

  # run both float and double with tsvc_2_5
  python3 run_sweep.py --precision both --tsvc-version tsvc_2_5

  # full grid on a Linux cluster
  python3 run_sweep.py --compilers clang gcc icpx --cost-models default cheap unlimited disabled --cpus intel_xeon amd_epyc

valid compilers   : {", ".join(ALL_COMPILERS)}
valid cost-models : {", ".join(ALL_COST_MODELS)}
valid cpus        : {", ".join(ALL_CPUS)}
valid versions    : {", ".join(TSVC_VERSION_CONFIG)}
valid precisions  : {", ".join(ALL_PRECISIONS)}
        """,
    )
    ap.add_argument(
        "--compilers",
        nargs="+",
        default=["clang"],
        choices=ALL_COMPILERS,
        metavar="COMPILER",
        help=f"Compilers to sweep. Choices: {', '.join(ALL_COMPILERS)}. (default: clang)",
    )
    ap.add_argument(
        "--cost-models",
        nargs="+",
        default=list(ALL_COST_MODELS),
        choices=ALL_COST_MODELS,
        metavar="MODEL",
        help=f"Cost models to sweep. Choices: {', '.join(ALL_COST_MODELS)}. (default: all)",
    )
    ap.add_argument(
        "--cpus",
        nargs="+",
        default=["apple_m_series"],
        choices=ALL_CPUS,
        metavar="CPU",
        help=f"CPU targets to sweep. Choices: {', '.join(ALL_CPUS)}. (default: apple_m_series)",
    )
    ap.add_argument(
        "--precision",
        default="double",
        choices=ALL_PRECISIONS,
        help=(
            "Which precision variants to compile. "
            "'both' runs double and float in sequence into separate subfolders. "
            "(default: double)"
        ),
    )
    ap.add_argument(
        "--tsvc-version",
        default="tsvc_2",
        choices=list(TSVC_VERSION_CONFIG),
        metavar="VERSION",
        help=f"TSVC version to use. Choices: {', '.join(TSVC_VERSION_CONFIG)}. (default: tsvc_2)",
    )
    ap.add_argument(
        "--cpp-kernels",
        default=None,
        metavar="DIR",
        help="Override C++ microkernels directory (default: version-specific, see TSVC_VERSION_CONFIG).",
    )
    ap.add_argument(
        "--dace-kernels",
        default=None,
        metavar="DIR",
        help="Override DaCe microkernels directory (default: version-specific, see TSVC_VERSION_CONFIG).",
    )
    ap.add_argument(
        "--out-cpp",
        default=None,
        metavar="DIR",
        help="Root output folder for C++ results. Defaults to results_cpp/<tsvc-version>/.",
    )
    ap.add_argument(
        "--out-dace",
        default=None,
        metavar="DIR",
        help="Root output folder for DaCe results. Defaults to results_dace/<tsvc-version>/.",
    )
    ap.add_argument(
        "-j", "--jobs",
        default=6,
        type=int,
        metavar="N",
        help="Parallel compile jobs (default: 6).",
    )
    return ap.parse_args()


def run_precision_sweep(
    precision: str,
    args,
    tsvc_module: str,
    cpp_kernels: str,
    dace_kernels: str,
    base_cpp: pathlib.Path,
    base_dace: pathlib.Path,
):
    """Run a full compiler/cost-model/cpu sweep for one precision variant."""
    key = (precision, args.tsvc_version)
    if key not in _PRECISION_PATTERNS:
        raise KeyError(
            f"No glob pattern defined for precision={precision!r}, "
            f"tsvc_version={args.tsvc_version!r}. Add it to _PRECISION_PATTERNS."
        )
    pattern_cpp, pattern_dace = _PRECISION_PATTERNS[key]

    # When running both precisions, nest under a precision subfolder:
    #   results_cpp/tsvc_2/double/clang_apple_m_series_default/
    #   results_cpp/tsvc_2/float/clang_apple_m_series_default/
    if args.precision == "both":
        output_cpp  = base_cpp  / precision
        output_dace = base_dace / precision
    else:
        output_cpp  = base_cpp
        output_dace = base_dace

    output_cpp.mkdir(parents=True, exist_ok=True)
    output_dace.mkdir(parents=True, exist_ok=True)

    scripts_dir = pathlib.Path("scripts")
    scripts_dir.mkdir(exist_ok=True)

    named_scripts = []
    for compiler in args.compilers:
        for cost_model in args.cost_models:
            for cpu in args.cpus:
                name = f"{compiler}_{cpu}_{cost_model}"
                named_scripts.append((name, compiler, cost_model, cpu))
                script_path = scripts_dir / f"source.{name}.sh"
                subprocess.run([
                    "vectra-source-sh",
                    "--compiler", compiler,
                    "--cost-model", cost_model,
                    "--cpu", cpu,
                    "--out", str(script_path)
                ], check=True)

    total = len(named_scripts)
    for i, (name, compiler, cost_model, cpu) in enumerate(named_scripts, 1):
        print(f"\n=== [{i}/{total}] [{precision}] {name} ===")

        script_path = scripts_dir / f"source.{name}.sh"
        source_env = subprocess.run(
            ["bash", "-c", f"source {script_path} && env"],
            capture_output=True, text=True, check=True
        )
        env = {**os.environ}
        for line in source_env.stdout.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                env[k] = v

        if platform.system() == "Darwin":
            if compiler == "clang":
                env["CXX"] = "clang++"
                env["CXX_COMPILER"] = "clang"
                env["DACE_compiler_cpu_executable"] = "clang++"
            elif compiler == "gcc":
                env["CXX"] = "/opt/homebrew/bin/g++-15"
                env["CXX_COMPILER"] = "gcc"
                env["DACE_compiler_cpu_executable"] = "/opt/homebrew/bin/g++-15"

        # ── CPP ───────────────────────────────────────────────────────────────
        cpp_out_dir   = output_cpp / name
        cpp_build_dir = cpp_out_dir / "build"
        cpp_out_dir.mkdir(parents=True, exist_ok=True)
        cpp_build_dir.mkdir(parents=True, exist_ok=True)

        result_cpp = subprocess.run([
            "python3", "-m", f"{tsvc_module}.compile_cpp_kernels",
            cpp_kernels,
            "-b", str(cpp_build_dir),
            "--pattern", pattern_cpp,
            "--vec-report",
            "--vec-report-out", str(cpp_out_dir / "vec_report.txt"),
            "--force", f"-j{args.jobs}"
        ], capture_output=True, text=True, env=env)

        (cpp_out_dir / "stdout.txt").write_text(result_cpp.stdout)
        (cpp_out_dir / "stderr.txt").write_text(result_cpp.stderr)
        print(f"  CPP  {'OK' if result_cpp.returncode == 0 else 'FAILED'} — {cpp_out_dir}/")

        # ── DaCe ──────────────────────────────────────────────────────────────
        dace_out_dir   = output_dace / name
        dace_build_dir = dace_out_dir / "build"
        dace_out_dir.mkdir(parents=True, exist_ok=True)
        dace_build_dir.mkdir(parents=True, exist_ok=True)

        result_dace = subprocess.run([
            "python3", "-m", f"{tsvc_module}.compile_dace_kernels",
            dace_kernels,
            "-b", str(dace_build_dir),
            "--pattern", pattern_dace,
            "--vec-report",
            "--vec-report-out", str(dace_out_dir / "vec_report.txt"),
            "--force", f"-j{args.jobs}"
        ], capture_output=True, text=True, env=env)

        (dace_out_dir / "stdout.txt").write_text(result_dace.stdout)
        (dace_out_dir / "stderr.txt").write_text(result_dace.stderr)
        print(f"  DaCe {'OK' if result_dace.returncode == 0 else 'FAILED'} — {dace_out_dir}/")


def main():
    args = parse_args()

    vcfg = TSVC_VERSION_CONFIG[args.tsvc_version]
    tsvc_module  = vcfg["module"]
    cpp_kernels  = args.cpp_kernels  or vcfg["cpp_kernels_dir"]
    dace_kernels = args.dace_kernels or vcfg["dace_kernels_dir"]

    base_cpp  = pathlib.Path(args.out_cpp  or f"results_cpp/{args.tsvc_version}")
    base_dace = pathlib.Path(args.out_dace or f"results_dace/{args.tsvc_version}")

    print(f"TSVC version : {args.tsvc_version}  (module: {tsvc_module})")
    print(f"CPP kernels  : {cpp_kernels}")
    print(f"DaCe kernels : {dace_kernels}")
    print(f"CPP output   : {base_cpp}")
    print(f"DaCe output  : {base_dace}")
    print(f"Compilers    : {args.compilers}")
    print(f"Cost models  : {args.cost_models}")
    print(f"CPUs         : {args.cpus}")
    print(f"Precision    : {args.precision}")

    precisions = ["double", "float"] if args.precision == "both" else [args.precision]

    for precision in precisions:
        print(f"\n{'='*60}")
        print(f"  Precision sweep: {precision.upper()}")
        print(f"{'='*60}")
        run_precision_sweep(
            precision=precision,
            args=args,
            tsvc_module=tsvc_module,
            cpp_kernels=cpp_kernels,
            dace_kernels=dace_kernels,
            base_cpp=base_cpp,
            base_dace=base_dace,
        )


if __name__ == "__main__":
    main()