"""Apply a :class:`FlagSet` to DaCe's ``compiler.cpu.*`` config.

DaCe's default C++ compiler is whatever CMake's ``find_program``
resolves (typically ``c++`` -> ``g++``); SDFG compilation runs through
CMake so the compiler choice + extra flags live under
``compiler.cpu.executable`` and ``compiler.cpu.args``. This module
makes that wiring explicit so direct C++ builds and DaCe-generated
builds always agree on (compiler, cost-model, math).
"""
from __future__ import annotations

from typing import Optional

from .flags import Compiler, CostModel, FlagSet, get_flags

# Flags DaCe / CMake adds itself; stripping them avoids duplicate-arg
# warnings on the nvcc / clang command line.
_DACE_MANAGED_COMPILE: frozenset = frozenset({"-fPIC", "-shared", "-MMD", "-MP", "-std=c++17"})
_DACE_MANAGED_LINK: frozenset = frozenset({"-shared"})


def configure_dace(flag_set: Optional[FlagSet] = None,
                   *,
                   compiler: Optional[Compiler] = None,
                   cost_model: Optional[CostModel] = None,
                   math: bool = False,
                   cpu: Optional[str] = None,
                   openmp_sections: bool = True) -> FlagSet:
    """Apply ``flag_set`` (or a freshly-resolved one) to DaCe.

    Two call styles:

    1. ``configure_dace(flag_set)`` -- use an already-resolved set.
    2. ``configure_dace(compiler=..., cost_model=..., math=..., cpu=...)``
       -- resolve via :func:`get_flags` and apply.

    The returned :class:`FlagSet` is also what was applied; callers can
    inspect ``flag_set.compile_flags`` for logging.
    """
    if flag_set is None:
        if compiler is None or cost_model is None:
            raise TypeError("configure_dace requires either flag_set or both compiler+cost_model")
        flag_set = get_flags(compiler, cost_model, math=math, cpu=cpu)

    import dace.config  # local import so the module doesn't hard-depend on dace at import time

    dace.config.Config.set("compiler", "cpu", "executable", value=flag_set.compiler.executable())

    extra_compile = " ".join(f for f in flag_set.compile_flags if f not in _DACE_MANAGED_COMPILE)
    dace.config.Config.set("compiler", "cpu", "args", value=extra_compile)

    extra_link = " ".join(f for f in flag_set.link_flags if f not in _DACE_MANAGED_LINK)
    if extra_link:
        dace.config.Config.set("compiler", "cpu", "libs", value=extra_link)

    if openmp_sections:
        dace.config.Config.set("compiler", "cpu", "openmp_sections", value=True)

    return flag_set


def detect_default_dace_cxx() -> str:
    """Return whatever DaCe currently considers the C++ compiler.

    Useful for diagnostics: ``print(detect_default_dace_cxx())`` reveals
    the resolved compiler before any :func:`configure_dace` call. DaCe
    falls back to ``c++`` if its config entry is empty.
    """
    import dace.config
    cxx = dace.config.Config.get("compiler", "cpu", "executable")
    return cxx or "c++"
