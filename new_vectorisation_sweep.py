#!/usr/bin/env python3
"""run_sweep.py — CPP + DaCe vectorization sweep across compiler/cost-model/CPU."""

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
_PRECISION_PATTERNS: dict = {
    ("double", "tsvc_2"):   ("*_d_single.cpp", "*_d_single.py"),
    ("float",  "tsvc_2"):   ("*_f_single.cpp", "*_f_single.py"),
    ("double", "tsvc_2_5"): ("*_d.cpp",        "*_d.py"),
    ("float",  "tsvc_2_5"): ("*_f.cpp",        "*_f.py"),
}


# ── Vectorization remark flags per compiler ────────────────────────────────────
_VEC_REMARK_COMPILE_FLAGS = {
    "clang": "-Rpass=loop-vectorize -Rpass-missed=loop-vectorize -Rpass-analysis=loop-vectorize",
    "gcc":   "-fopt-info-vec-optimized -fopt-info-vec-missed",
    "icpx":  "-Rpass=loop-vectorize -Rpass-missed=loop-vectorize -qopt-report=5 -qopt-report-phase=vec",
}

# ── Cost-model optimisation flags ─────────────────────────────────────────────
# These are injected into CXXFLAGS so that compile_dace.py's
# _extra_flags_from_env() can forward them when regenerating .rpt files.
# This ensures the vec report reflects the actual cost-model configuration,
# not just whatever flags DaCe baked into flags.make.
#
# The sourced shell script already sets the compiler driver / linker correctly;
# these flags are the optimisation-level additions that differ per cost-model.
_COST_MODEL_CXXFLAGS = {
    "default":  "-O2",
    "cheap":    "-O1",
    "unlimited": "-O3 -ffast-math -march=native",
    "disabled": "-O0 -fno-vectorize",
}

# GCC equivalents (fno-vectorize is -fno-tree-vectorize for GCC)
_COST_MODEL_CXXFLAGS_GCC = {
    "default":  "-O2",
    "cheap":    "-O1",
    "unlimited": "-O3 -ffast-math -march=native",
    "disabled": "-O0 -fno-tree-vectorize",
}


def _cost_model_flags(compiler: str, cost_model: str) -> str:
    """Return the optimisation flags for a given compiler/cost-model pair."""
    if compiler == "gcc":
        return _COST_MODEL_CXXFLAGS_GCC.get(cost_model, "")
    return _COST_MODEL_CXXFLAGS.get(cost_model, "")


def _inject_vec_remark_flags(env: dict, compiler: str) -> dict:
    """
    Append vectorization remark flags to CXXFLAGS / DACE_compiler_cpu_args
    in *env* so both the CPP build system and DaCe's CMake invocation pass
    them through to the compiler.

    Returns the modified env dict (a copy is made — the original is unchanged).
    """
    env = dict(env)
    remark_flags = _VEC_REMARK_COMPILE_FLAGS.get(compiler, "")
    if not remark_flags:
        return env

    existing_cxx = env.get("CXXFLAGS", "")
    env["CXXFLAGS"] = f"{existing_cxx} {remark_flags}".strip()

    existing_dace = env.get("DACE_compiler_cpu_args", "")
    env["DACE_compiler_cpu_args"] = f"{existing_dace} {remark_flags}".strip()

    return env


def _inject_cost_model_flags(env: dict, compiler: str, cost_model: str) -> dict:
    """
    Inject cost-model optimisation flags into CXXFLAGS so that
    compile_dace.py's _extra_flags_from_env() forwards them when regenerating
    per-kernel .rpt files.  Without this, DaCe vec reports always reflect the
    same baseline regardless of cost-model, because flags.make only records
    what DaCe itself decided — not env-injected optimisation flags.

    These flags are placed at the START of CXXFLAGS so that any later
    cost-model-specific overrides from the sourced shell script take precedence.

    Returns a modified copy of env.
    """
    env = dict(env)
    flags = _cost_model_flags(compiler, cost_model)
    if not flags:
        return env

    existing = env.get("CXXFLAGS", "")
    # Cost-model flags lead; existing (sourced) flags trail so compiler-driver
    # settings from vectra-source-sh are not overridden.
    env["CXXFLAGS"] = f"{flags} {existing}".strip()

    return env


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

  # enable runtime timing
  python3 run_sweep.py --time --reps 50

  # full grid on a Linux cluster
  python3 run_sweep.py --compilers clang gcc icpx --cost-models default cheap unlimited disabled --cpus intel_xeon amd_epyc

valid compilers   : {", ".join(ALL_COMPILERS)}
valid cost-models : {", ".join(ALL_COST_MODELS)}
valid cpus        : {", ".join(ALL_CPUS)}
valid versions    : {", ".join(TSVC_VERSION_CONFIG)}
valid precisions  : {", ".join(ALL_PRECISIONS)}
        """,
    )
    ap.add_argument("--compilers", nargs="+", default=["clang"], choices=ALL_COMPILERS,
                    metavar="COMPILER",
                    help=f"Compilers to sweep. Choices: {', '.join(ALL_COMPILERS)}. (default: clang)")
    ap.add_argument("--cost-models", nargs="+", default=list(ALL_COST_MODELS), choices=ALL_COST_MODELS,
                    metavar="MODEL",
                    help=f"Cost models to sweep. Choices: {', '.join(ALL_COST_MODELS)}. (default: all)")
    ap.add_argument("--cpus", nargs="+", default=["apple_m_series"], choices=ALL_CPUS,
                    metavar="CPU",
                    help=f"CPU targets to sweep. Choices: {', '.join(ALL_CPUS)}. (default: apple_m_series)")
    ap.add_argument("--precision", default="double", choices=ALL_PRECISIONS,
                    help="Which precision variants to compile. 'both' runs double and float. (default: double)")
    ap.add_argument("--tsvc-version", default="tsvc_2", choices=list(TSVC_VERSION_CONFIG),
                    metavar="VERSION",
                    help=f"TSVC version to use. Choices: {', '.join(TSVC_VERSION_CONFIG)}. (default: tsvc_2)")
    ap.add_argument("--cpp-kernels", default=None, metavar="DIR",
                    help="Override C++ microkernels directory.")
    ap.add_argument("--dace-kernels", default=None, metavar="DIR",
                    help="Override DaCe microkernels directory.")
    ap.add_argument("--out-cpp", default=None, metavar="DIR",
                    help="Root output folder for C++ results. Defaults to results_cpp/<tsvc-version>/.")
    ap.add_argument("--out-dace", default=None, metavar="DIR",
                    help="Root output folder for DaCe results. Defaults to results_dace/<tsvc-version>/.")
    ap.add_argument("-j", "--jobs", default=6, type=int, metavar="N",
                    help="Parallel compile jobs (default: 6).")
    ap.add_argument("--time", action="store_true",
                    help="Enable runtime timing after each compile step.")
    ap.add_argument("--reps", type=int, default=100, metavar="N",
                    help="Timing repetitions per kernel when --time is set (default: 100).")
    ap.add_argument("--len-1d", type=int, default=1024, metavar="N", dest="len_1d",
                    help="Array length used during timing (default: 1024).")
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

    output_cpp  = base_cpp  / precision
    output_dace = base_dace / precision

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

        # ── Step 1: inject cost-model optimisation flags into CXXFLAGS ────────
        # compile_dace.py reads CXXFLAGS via _extra_flags_from_env() and
        # forwards them when regenerating per-kernel .rpt files, so the vec
        # report reflects the actual cost-model configuration.
        env = _inject_cost_model_flags(env, compiler, cost_model)

        # ── Step 2: append vectorization remark flags ──────────────────────────
        # Purely diagnostic — never changes vectorization decisions.
        # Placed AFTER cost-model flags so they trail in CXXFLAGS and are not
        # accidentally overridden.
        env = _inject_vec_remark_flags(env, compiler)

        # ── CPP ───────────────────────────────────────────────────────────────
        cpp_out_dir   = output_cpp / name
        cpp_build_dir = cpp_out_dir / "build"
        cpp_out_dir.mkdir(parents=True, exist_ok=True)
        cpp_build_dir.mkdir(parents=True, exist_ok=True)

        cpp_cmd = [
            "python3", "-m", f"{tsvc_module}.compile_cpp_kernels",
            cpp_kernels,
            "-b", str(cpp_build_dir),
            "--pattern", pattern_cpp,
            "--vec-report",
            "--vec-report-out", str(cpp_out_dir / "vec_report.txt"),
            "--force", f"-j{args.jobs}",
        ]
        if args.time:
            cpp_cmd += [
                "--time",
                "--reps", str(args.reps),
                "--len-1d", str(args.len_1d),
                "--timing-out", str(cpp_out_dir / "timing_report.csv"),
            ]

        result_cpp = subprocess.run(cpp_cmd, capture_output=True, text=True, env=env)
        (cpp_out_dir / "stdout.txt").write_text(result_cpp.stdout)
        (cpp_out_dir / "stderr.txt").write_text(result_cpp.stderr)
        print(f"  CPP  {'OK' if result_cpp.returncode == 0 else 'FAILED'} — {cpp_out_dir}/")

        # ── DaCe ──────────────────────────────────────────────────────────────
        dace_out_dir   = output_dace / name
        dace_build_dir = dace_out_dir / "build"
        dace_out_dir.mkdir(parents=True, exist_ok=True)
        dace_build_dir.mkdir(parents=True, exist_ok=True)

        dace_cmd = [
            "python3", "-m", f"{tsvc_module}.compile_dace_kernels",
            dace_kernels,
            "-b", str(dace_build_dir),
            "--pattern", pattern_dace,
            "--vec-report",
            "--vec-report-out", str(dace_out_dir / "vec_report.txt"),
            "--force", f"-j{args.jobs}",
        ]
        if args.time:
            dace_cmd += [
                "--time",
                "--reps", str(args.reps),
                "--len-1d", str(args.len_1d),
                "--timing-out", str(dace_out_dir / "timing_report.csv"),
                "--kernel-timeout", "120",
            ]

        result_dace = subprocess.run(dace_cmd, capture_output=True, text=True, env=env)
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
    print(f"Timing       : {'enabled — ' + str(args.reps) + ' reps, len_1d=' + str(args.len_1d) if args.time else 'disabled (pass --time to enable)'}")

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