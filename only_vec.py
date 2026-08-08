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
# Single source of truth: vectra_artifacts.compilers.flags.get_flags(), the
# SAME canonical (compiler, cost-model, cpu) matrix that vectra-source-sh
# already uses to write CXX/CXX_COSTMODEL/EXTRA_FLAGS into source.sh for the
# CPP build (via compiler_config.py). We reuse it here — rather than keeping
# a second, hand-written flag table — so the DaCe build is compiled with
# byte-identical optimisation flags to the CPP build for the "same" sweep
# cell. A previous version of this file kept its own _COST_MODEL_CXXFLAGS /
# _CPU_ISA_INFO tables that (a) disagreed with the canonical matrix and
# (b) were only ever forwarded into DACE_compiler_cpu_args as diagnostic
# remark flags — never the actual -O3/-march/-fvectorize flags — so
# --cost-models and --cpus silently had *no effect* on DaCe's compiled
# machine code. See _build_env() below.
from vectra_artifacts.compilers import Compiler, CostModel, get_flags
from vectra_artifacts.compilers.flags import get_remark_flags
from vectra_artifacts.compilers.dace_setup import _DACE_MANAGED_COMPILE, _DACE_MANAGED_LINK


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
    """
    Resolve the canonical (compiler, cost-model, cpu) flag set and push it
    into every env var the CPP *and* DaCe compile subprocesses actually
    read, so both are built with the same flags for a given sweep cell.

    - CPP: `python3 -m {tsvc_module}.compile_cpp_kernels` imports
      compiler_config.py fresh, which re-resolves get_flags() itself from
      CXX / CXX_COMPILER / CXX_COSTMODEL / CPU_NAME. We set those here too
      (not just rely on the source.sh vectra-source-sh already wrote) so
      this function is the one place that has to be right.
    - DaCe: dace.config.Config treats DACE_compiler_cpu_executable /
      DACE_compiler_cpu_args as full-replacement env overrides (see
      dace/config.py's `DACE_<hierarchy>` lookup — it *replaces* the
      config value, it does not merge with it). That means these two
      vars must carry the *complete* resolved flag set, not just the
      diagnostic remark flags, or --cost-models / --cpus silently has no
      effect on DaCe's actual compiled/disassembled code.
    """
    env = dict(env)

    comp_enum = Compiler(compiler)
    cm_enum   = CostModel(cost_model)
    flag_set  = get_flags(comp_enum, cm_enum, cpu=cpu)

    cxx_executable = flag_set.compiler.executable()
    if platform.system() == "Darwin":
        if compiler == "clang":
            cxx_executable = "clang++"
        elif compiler == "gcc":
            # Plain "g++" on macOS is usually a Clang shim; force the real
            # Homebrew GCC so compiler=="gcc" actually means GCC.
            cxx_executable = "/opt/homebrew/bin/g++-15"

    env["CXX"]           = cxx_executable
    env["CXX_COMPILER"]  = compiler
    env["CXX_COSTMODEL"] = cost_model
    env["CPU_NAME"]      = cpu

    remark_flags = list(get_remark_flags(comp_enum))

    dace_compile_flags = [f for f in flag_set.compile_flags if f not in _DACE_MANAGED_COMPILE]
    env["DACE_compiler_cpu_executable"] = cxx_executable
    env["DACE_compiler_cpu_args"] = " ".join(dace_compile_flags + remark_flags).strip()

    dace_link_flags = [f for f in flag_set.link_flags if f not in _DACE_MANAGED_LINK]
    if dace_link_flags:
        env["DACE_compiler_cpu_libs"] = " ".join(dace_link_flags)

    # Only consumed by compile_dace.py's diagnostic -S re-run
    # (_extra_flags_from_env), which appends CXXFLAGS *after* the flags it
    # already parsed out of the real build's flags.make. Must reuse the
    # same _DACE_MANAGED_COMPILE-filtered list (not the raw compile_flags):
    # flag_set.compile_flags still carries "-std=c++17", and since the LAST
    # -std= flag on a clang/gcc command line wins, that would silently
    # downgrade the diagnostic recompile below the C++20 DaCe's own
    # generated headers require (e.g. std::bit_cast) — the -S step would
    # then fail outright, vec_check.s would never be written, and every
    # kernel would misreport as "not vectorized" regardless of cost-model.
    env["CXXFLAGS"] = " ".join(dace_compile_flags + remark_flags).strip()

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