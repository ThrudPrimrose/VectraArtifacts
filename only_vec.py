#!/usr/bin/env python3
"""
only_vec.py — compile CPP + DaCe TSVC kernels for one or more
compiler / cost-model / CPU combinations and generate vectorisation reports.

Timing is intentionally separated — run run_timing_sweep.py after this.

Sharding
--------
When launched via `srun` with multiple tasks, each task automatically picks
up SLURM_PROCID / SLURM_NTASKS and only processes its slice of the full
(precision, compiler, cost-model, cpu) run matrix. You can also override
manually with --shard-id / --num-shards for local testing.

Examples
--------
# Single cell (equivalent to the hardcoded original)
python3 only_vec.py --compilers clang --cost-models unlimited --cpus apple_m_series

# Multiple compilers, all cost-models, double + float
python3 only_vec.py --compilers clang gcc --cost-models default cheap unlimited disabled --cpus apple_m_series --precision both

# tsvc_2_5 layout
python3 only_vec.py --tsvc-version tsvc_2_5 --compilers clang --cost-models unlimited --cpus apple_m_series

# Manual shard override (e.g. local testing of shard 2 of 4)
python3 only_vec.py --compilers clang gcc --cost-models default cheap unlimited disabled --cpus arm_grace --shard-id 2 --num-shards 4

# Cluster usage (each srun task auto-detects its shard from SLURM env vars)
srun python3 only_vec.py --compilers clang gcc --cost-models default cheap unlimited disabled --cpus arm_grace -j ${SLURM_CPUS_PER_TASK}
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
_COST_MODEL_CXXFLAGS = {
    "default":   "-O3 -march=native -fno-math-errno -fno-trapping-math -fno-signed-zeros -fvectorize",
    # "cheap":     "-O3 -march=native -fno-math-errno -fno-trapping-math -fno-signed-zeros -fvectorize",
    "unlimited": "-O3 -march=native -fno-math-errno -fno-trapping-math -fno-signed-zeros ",
    "disabled":  "-O3 -march=native -fno-math-errno -fno-trapping-math -fno-signed-zeros -fno-vectorize -fno-slp-vectorize",
}
_COST_MODEL_CXXFLAGS_GCC = {
    "default":   "-O3 -march=native -fno-math-errno -fno-trapping-math -fno-signed-zeros -fno-signaling-nans -ftree-vectorize -fvect-cost-model=dynamic",
    "cheap":     "-O3 -march=native -fno-math-errno -fno-trapping-math -fno-signed-zeros -fno-signaling-nans -ftree-vectorize -fvect-cost-model=cheap",
    "unlimited": "-O3 -march=native -fno-math-errno -fno-trapping-math -fno-signed-zeros -fno-signaling-nans -fno-vect-cost-model",
    "disabled":  "-O3 -march=native -fno-math-errno -fno-trapping-math -fno-signed-zeros -fno-signaling-nans -fno-tree-vectorize",
}


# ── Vectorisation remark flags ─────────────────────────────────────────────────
_VEC_REMARK_FLAGS = {
    "clang": "-Rpass=.* -Rpass-missed=.*",
    "gcc":   "-fopt-info-all",
    "icpx":  "-Rpass=loop-vectorize -Rpass-missed=loop-vectorize -qopt-report=5 -qopt-report-phase=vec",
}

import platform as _platform

# ── CPU → ISA-specific vectorization width config ─────────────────────────────
# Each entry: (isa_family, native_width_bits)
#   isa_family: "x86" -> use -mprefer-vector-width
#               "sve" -> use -msve-vector-bits (ARM SVE cores)
#               "neon" -> no ISA-level width knob; use LLVM -force-vector-width
_CPU_ISA_INFO = {
    "amd_epyc":        ("x86",  256),   # Zen2/3, AVX2, 256-bit native
    "amd_epyc_genoa":  ("x86",  512),   # Zen4, AVX-512, 512-bit native
    "intel_xeon":      ("x86",  512),   # Skylake+ AVX-512
    "arm_grace":       ("sve",  128),   # Neoverse V2, SVE2 128-bit vectors
    "fugaku_a64fx":    ("sve",  512),   # A64FX, SVE 512-bit vectors
    "apple_m_series":  ("neon", 128),   # NEON only, 128-bit, no SVE
    "ibm_power":       ("altivec", 128),# VSX/Altivec, 128-bit
}

# Fallback "elements-per-vector" used for -force-vector-width (LLVM internal,
# expressed in elements, not bits — assume 32-bit float/int elements as base unit)
def _force_vector_width_elems(width_bits: int) -> int:
    return max(1, width_bits // 32)


def _clang_vector_width_flags(cpu: str) -> str:
    """
    Return the correct Clang forced-vectorization-width flag(s) for a given
    target CPU, matching its native ISA (x86 AVX*, ARM SVE, ARM NEON, POWER).
    Used only for the 'unlimited' cost-model, where we want the vectorizer
    to use the *maximum* natural width rather than whatever the cost model
    picks.
    """
    info = _CPU_ISA_INFO.get(cpu)
    if info is None:
        return ""
    isa_family, width_bits = info

    if isa_family == "x86":
        return f"-mprefer-vector-width={width_bits}"
    elif isa_family == "sve":
        return f"-msve-vector-bits={width_bits}"
    else:
        # NEON-only ARM (e.g. Apple M-series) or POWER/Altivec: no ISA-level
        # width flag exists in Clang, so force it at the LLVM loop-vectorizer
        # level directly, in elements.
        elems = _force_vector_width_elems(width_bits)
        return f"-mllvm -force-vector-width={elems}"


def _host_arch_matches_target(cpu: str) -> bool:
    """
    Sanity check: warn (but don't fail) if the host machine's actual
    architecture (arm64 vs x86_64) doesn't match the requested --cpus target,
    since forced-width flags are only meaningful when compiling natively for
    that ISA (no cross-compilation toolchain assumed here).
    """
    host_machine = _platform.machine().lower()
    host_is_arm = host_machine in ("arm64", "aarch64")
    target_is_arm = _CPU_ISA_INFO.get(cpu, ("x86", 0))[0] in ("sve", "neon")
    return host_is_arm == target_is_arm


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


def _build_env(env: dict, compiler: str, cost_model: str, cpu: str) -> dict:
    """Apply macOS overrides, cost-model flags, remark flags, and
    architecture-correct forced vector width (clang + unlimited only)."""
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

    # ── Forced vectorization width, arch-correct, clang + unlimited only ──
    if compiler == "clang" and cost_model == "unlimited":
        width_flag = _clang_vector_width_flags(cpu)
        if width_flag:
            if not _host_arch_matches_target(cpu):
                print(
                    f"  [warn] host arch {_platform.machine()} != target ISA "
                    f"for cpu={cpu}; forced width flag may not apply natively",
                    file=sys.stderr,
                )
            existing = env.get("CXXFLAGS", "")
            env["CXXFLAGS"] = f"{existing} {width_flag}".strip()

    remark_flags = _VEC_REMARK_FLAGS.get(compiler, "")
    if remark_flags:
        env["CXXFLAGS"] = f"{env.get('CXXFLAGS', '')} {remark_flags}".strip()
        env["DACE_compiler_cpu_args"] = (
            f"{env.get('DACE_compiler_cpu_args', '')} {remark_flags}".strip()
        )

    return env


def _dump_asm_from_objects(build_dir: pathlib.Path, asm_dir: pathlib.Path) -> None:
    """Disassemble all .o files under build_dir using objdump and write
    <kernel>.s files to asm_dir.  Works for both CPP and DaCe builds."""
    asm_dir.mkdir(parents=True, exist_ok=True)
    obj_files = sorted(build_dir.rglob("*.o"))
    if not obj_files:
        print(f"  [asm] no .o files found under {build_dir}/", file=sys.stderr)
        return
    print(f"  [asm] disassembling {len(obj_files)} object file(s) -> {asm_dir}/")
    ok = 0
    for obj in obj_files:
        out = asm_dir / (obj.stem + ".s")
        res = subprocess.run(
            ["objdump", "-d", str(obj)],
            capture_output=True, text=True,
        )
        if res.returncode == 0:
            out.write_text(res.stdout)
            ok += 1
        else:
            print(f"  [asm] FAIL {obj.name}: {res.stderr[:300]}", file=sys.stderr)
    print(f"  [asm] {ok}/{len(obj_files)} assembly files written.")


def _resolve_shard(args) -> tuple[int, int]:
    """
    Resolve (shard_id, num_shards).

    Priority: explicit CLI flags > SLURM env vars > single-shard default.
    """
    shard_id = args.shard_id
    num_shards = args.num_shards

    if shard_id is None:
        shard_id = int(os.environ.get("SLURM_PROCID", 0))
    if num_shards is None:
        num_shards = int(os.environ.get("SLURM_NTASKS", 1))

    if num_shards < 1:
        raise ValueError(f"--num-shards must be >= 1, got {num_shards}")
    if not (0 <= shard_id < num_shards):
        raise ValueError(f"--shard-id {shard_id} out of range for --num-shards {num_shards}")

    return shard_id, num_shards


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
    ap.add_argument(
        "--shard-id", type=int, default=None, metavar="N",
        help="0-indexed shard this process handles. Defaults to $SLURM_PROCID if unset.",
    )
    ap.add_argument(
        "--num-shards", type=int, default=None, metavar="K",
        help="Total number of shards. Defaults to $SLURM_NTASKS if unset (i.e. 1 = no sharding).",
    )
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

    # Generate the environment script if it doesn't exist yet.
    # NOTE: with multiple shards writing concurrently, different shards may
    # need *different* cells, so this is naturally race-free as long as no
    # two shards are ever assigned the same cell (guaranteed by the
    # strided slicing in main()).
    print("debug before source \n")
    if not script_path.exists():
        subprocess.run([
            "vectra-source-sh",
            "--compiler",   compiler,
            "--cost-model", cost_model,
            "--cpu",        cpu,
            "--out",        str(script_path),
        ], check=True)
    print("debug after source \n")
    env = _build_env(_source_env(script_path), compiler, cost_model, cpu)
    print("debug after build env \n")
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
        print("debug before CPP \n")
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

        if result.returncode == 0:
            _dump_asm_from_objects(cpp_build_dir, cpp_out_dir / "asm")

    # ── DaCe ──────────────────────────────────────────────────────────────────
    if not skip_dace:
        dace_out_dir   = base_dace / precision / name
        dace_build_dir = dace_out_dir / "build"
        dace_out_dir.mkdir(parents=True, exist_ok=True)
        dace_build_dir.mkdir(parents=True, exist_ok=True)
        print("debug before DaCe \n")
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

        if result.returncode == 0:
            _dump_asm_from_objects(dace_build_dir, dace_out_dir / "asm")


def main(argv=None):
    print("debug 1 \n")
    args = parse_args(argv)
    print("debug 2 \n")
    vcfg         = TSVC_VERSION_CONFIG[args.tsvc_version]
    tsvc_module  = vcfg["module"]
    cpp_kernels  = args.cpp_kernels  or vcfg["cpp_kernels_dir"]
    dace_kernels = args.dace_kernels or vcfg["dace_kernels_dir"]

    # base_cpp  = pathlib.Path(args.out_cpp  or f"results_cpp/{args.tsvc_version}")
    # base_dace = pathlib.Path(args.out_dace or f"results_dace/{args.tsvc_version}")

    base_cpp  = pathlib.Path(args.out_cpp  or "results_cpp") / args.tsvc_version
    base_dace = pathlib.Path(args.out_dace or "results_dace") / args.tsvc_version

    precisions = ["double", "float"] if args.precision == "both" else [args.precision]

    # Build the FULL list of cells (compiler x cost-model x cpu)
    cells = [
        (f"{compiler}_{cpu}_{cost_model}", compiler, cost_model, cpu)
        for compiler   in args.compilers
        for cost_model in args.cost_models
        for cpu        in args.cpus
    ]

    # Flatten precision x cells into one master run list, then shard it.
    all_runs = [
        (precision, name, compiler, cost_model, cpu)
        for precision in precisions
        for (name, compiler, cost_model, cpu) in cells
    ]
    print("debug 3 \n")
    shard_id, num_shards = _resolve_shard(args)
    my_runs = all_runs[shard_id::num_shards]

    print(f"TSVC version : {args.tsvc_version}  (module: {tsvc_module})")
    print(f"CPP kernels  : {cpp_kernels}")
    print(f"DaCe kernels : {dace_kernels}")
    print(f"Compilers    : {args.compilers}")
    print(f"Cost models  : {args.cost_models}")
    print(f"CPUs         : {args.cpus}")
    print(f"Precisions   : {precisions}")
    print(f"Total runs   : {len(all_runs)}")
    print(f"Shard        : {shard_id} / {num_shards}  ->  {len(my_runs)} run(s) assigned to this process")
    print(f"Skip CPP     : {args.no_cpp}")
    print(f"Skip DaCe    : {args.no_dace}")

    for idx, (precision, name, compiler, cost_model, cpu) in enumerate(my_runs, 1):
        if compiler == "clang" and cost_model == "cheap":
            continue
        print(f"\\n=== [shard {shard_id}/{num_shards}] [{idx}/{len(my_runs)}] [{precision}] {name} ===")
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

    print(f"\\nDone. Shard {shard_id}/{num_shards} compiled {len(my_runs)} cell(s).")


if __name__ == "__main__":
    main()