"""Compiler-flag matrix + DaCe / shell integration.

Exports:

* :class:`Compiler` -- the three supported compilers (clang / gcc / icpx).
* :class:`CostModel` -- the three cost-model presets (default / cheap / no).
* :func:`get_flags` -- look up the canonical flag list for
  ``(compiler, cost_model, math)``.
* :func:`configure_dace` -- apply the flag set to DaCe's ``compiler.cpu.*``
  config so SDFG compilation uses the same compiler + flags as direct C++
  builds (replaces the older top-level ``compiler_config.configure_dace``).
* :func:`source_sh` -- emit a ``source.sh`` snippet that sets ``CXX``,
  ``CXX_COSTMODEL``, ``EXTRA_VEC_FLAGS``, ``EXTRA_FLAGS``, and ``LINK_FLAGS``
  so a downstream build can pick up the right combo via env vars.
"""
from .flags import (ArmAutovecPreference, BASELINE_FLAGS, LINK_BASE_FLAGS, Compiler, CostModel, FlagSet,
                    EXECUTABLE_BY_COMPILER, detect_local_vector_width, get_flags, iter_combinations,
                    vector_width_for_cpu)
from .dace_setup import configure_dace
from .source_sh import source_sh, write_source_sh

__all__ = [
    "ArmAutovecPreference",
    "BASELINE_FLAGS",
    "LINK_BASE_FLAGS",
    "Compiler",
    "CostModel",
    "FlagSet",
    "EXECUTABLE_BY_COMPILER",
    "configure_dace",
    "detect_local_vector_width",
    "get_flags",
    "iter_combinations",
    "vector_width_for_cpu",
    "source_sh",
    "write_source_sh",
]
