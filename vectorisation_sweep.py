import subprocess
import pathlib
import os
import platform



# List of all the permutations 
# compilers = ("clang", "gcc", "icpx") # icpx is a linux only compiler 
# cost_models = ("default", "cheap", "unlimited", "disabled") 
# cpu_archs = ("amd_epyc", "amd_epyc_genoa", "apple_m_series", "arm_grace", "fugaku_a64fx", "ibm_power", "intel_xeon")  
  
compilers = ("clang",)
#compilers = ("clang", "gcc") 
# cost_models = ("default", "cheap", "unlimited", "disabled") 
cost_models = ("unlimited", ) 
cpu_archs = ("apple_m_series", ) # for testing only this works on my laptop 

# Output root folders 
output_cpp = pathlib.Path("results_cpp")
output_dace = pathlib.Path("results_dace") 
output_cpp.mkdir(exist_ok=True) 
output_dace.mkdir(exist_ok=True)

scripts_dir = pathlib.Path("scripts")

# Generate scripts

named_scripts = []
for compiler in compilers:
    for cost_model in cost_models:
        for cpu in cpu_archs:
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

# Run for every permutation 

for name, compiler, cost_model, cpu in named_scripts:
    print(f"\n=== Running: {name} ===")

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

    # On macOS, override compiler to Apple Clang regardless of CXX_COMPILER.
    # Cost model flags (CXX_COSTMODEL, EXTRA_FLAGS) from source.sh are preserved.
    if platform.system() == "Darwin":
        if compiler == "clang":
            env["CXX"] = "clang++"
            env["CXX_COMPILER"] = "clang"
            env["DACE_compiler_cpu_executable"] = "clang++"
        elif compiler == "gcc":
            env["CXX"] = "/opt/homebrew/bin/g++-15"
            env["CXX_COMPILER"] = "gcc"
            env["DACE_compiler_cpu_executable"] = "/opt/homebrew/bin/g++-15"

    # ── CPP ───────────────────────────────────────────────────────────
    cpp_out_dir = output_cpp / name
    cpp_build_dir = cpp_out_dir / "build"
    cpp_out_dir.mkdir(parents=True, exist_ok=True)
    cpp_build_dir.mkdir(parents=True, exist_ok=True)

    result_cpp = subprocess.run([
        "python3", "-m", "tsvc_2.compile_cpp_kernels",
        "tsvc_2/tsvc_cpp_microkernels",
        "-b", str(cpp_build_dir),
        "--pattern", "*_d_single.cpp",
        "--vec-report",
        "--vec-report-out", str(cpp_out_dir / "vec_report.txt"),
        "--force", "-j6"
    ], capture_output=True, text=True, env=env)

    (cpp_out_dir / "stdout.txt").write_text(result_cpp.stdout)
    (cpp_out_dir / "stderr.txt").write_text(result_cpp.stderr)
    print(f"  CPP {'OK' if result_cpp.returncode == 0 else 'FAILED'} — {cpp_out_dir}/")

    # ── DaCe ──────────────────────────────────────────────────────────
    dace_out_dir = output_dace / name
    dace_build_dir = dace_out_dir / "build"
    dace_out_dir.mkdir(parents=True, exist_ok=True)
    dace_build_dir.mkdir(parents=True, exist_ok=True)

    result_dace = subprocess.run([
        "python3", "-m", "tsvc_2.compile_dace_kernels",
        "tsvc_2/tsvc_dace_microkernels",
        "-b", str(dace_build_dir),
        "--pattern", "*_d_single.py",
        "--vec-report",
        "--vec-report-out", str(dace_out_dir / "vec_report.txt"),
        "--force", "-j6"
    ], capture_output=True, text=True, env=env)

    (dace_out_dir / "stdout.txt").write_text(result_dace.stdout)
    (dace_out_dir / "stderr.txt").write_text(result_dace.stderr)
    print(f"  DaCe {'OK' if result_dace.returncode == 0 else 'FAILED'} — {dace_out_dir}/")