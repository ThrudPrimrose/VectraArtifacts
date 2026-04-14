"""
Shared compiler configuration for TSVC microkernels.

Imported by compile_kernel.py (C++ direct compilation) and
compile_dace_kernels.py (DaCe SDFG compilation).
"""

import os

CXX = os.environ.get("CXX", "c++")

COMPILE_FLAGS = [
    "-O3",
    "-std=c++17",
    "-fPIC",
    "-ffast-math",
    "-fstrict-aliasing",
    "-fno-math-errno",
    "-fopenmp",
    "-faligned-new",
    "-MMD",
    "-MP",
    "-Wall",
    "-Wextra",
    "-Wno-unused-parameter",
    "-Wno-unused-label",
]

LINK_FLAGS = [
    "-shared",
    "-fopenmp",
]

_cpu = os.environ.get("CPU_NAME", "")
if _cpu != "arm":
    COMPILE_FLAGS.append("-march=native")

_EXTRA = os.environ.get("EXTRA_FLAGS", "")
if _EXTRA:
    COMPILE_FLAGS.extend(_EXTRA.split())


def configure_dace():
    """
    Apply COMPILE_FLAGS and LINK_FLAGS to DaCe's config so that
    SDFG compilation uses the same compiler settings as direct C++ builds.
    """
    import dace.config

    dace.config.Config.set("compiler", "cpu", "executable", value=CXX)

    # Build the extra args string (skip flags DaCe/CMake sets itself)
    _DACE_MANAGED = {"-fPIC", "-shared", "-MMD", "-MP", "-std=c++17"}
    extra_args = " ".join(f for f in COMPILE_FLAGS if f not in _DACE_MANAGED)
    dace.config.Config.set("compiler", "cpu", "args", value=extra_args)

    # Linker flags (strip -shared, DaCe adds that)
    extra_link = " ".join(f for f in LINK_FLAGS if f != "-shared")
    if extra_link:
        dace.config.Config.set("compiler", "cpu", "libs", value=extra_link)

    # Use OpenMP
    dace.config.Config.set("compiler", "cpu", "openmp_sections", value=True)
