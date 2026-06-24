# debug_vec2.py
import pathlib, subprocess, re

kdir = pathlib.Path("results_dace/tsvc_2_5/clang_apple_m_series_unlimited/build/ext_modular_wrap_d")
build_root = kdir / "build"

# Find src/cpu .cpp
src_cpp = None
for c in sorted(build_root.rglob("src/cpu/*.cpp"), key=lambda p: len(p.parts), reverse=True):
    src_cpp = c
    break
print(f"src_cpp: {src_cpp}")

# Find flags.make (non-dacestub)
flags_make = None
for f in build_root.rglob("flags.make"):
    if "dacestub" not in f.parts[-2]:
        flags_make = f
        break
print(f"flags_make: {flags_make}")

if flags_make:
    text = flags_make.read_text()
    print("\n--- flags.make content ---")
    print(text[:1200])

    compiler_exe = ""
    for line in text.splitlines():
        m = re.match(r"#\s*compile\s+CXX\s+with\s+(\S+)", line)
        if m:
            compiler_exe = m.group(1)
            break
    print(f"\ncompiler_exe: {compiler_exe}")

    cxx_flags = []
    cxx_defines = []
    cxx_includes = []
    for line in text.splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        key, _, val = line.partition("=")
        key = key.strip(); val = val.strip()
        if re.match(r"CXX_FLAGS", key):
            cxx_flags = val.split()
            print(f"CXX_FLAGS key matched: {key!r}")
        elif key == "CXX_DEFINES":
            cxx_defines = val.split()
        elif key == "CXX_INCLUDES":
            cxx_includes = val.split()

    print(f"\ncxx_flags: {cxx_flags}")
    print(f"cxx_defines: {cxx_defines[:3]}...")
    print(f"cxx_includes: {cxx_includes[:3]}...")

    # Build and run the actual command
    cmd = [compiler_exe] + cxx_defines + cxx_includes + cxx_flags + ["-fsyntax-only", str(src_cpp)]
    print(f"\n--- command ---")
    print(" ".join(cmd[:8]), "...")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                            cwd=str(flags_make.parent.parent))
    print(f"\nreturncode: {result.returncode}")
    print(f"\n--- stderr (first 2000 chars) ---")
    print(result.stderr[:2000])
    print(f"\n--- stdout (first 500 chars) ---")
    print(result.stdout[:500])