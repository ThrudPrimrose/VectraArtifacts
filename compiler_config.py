"""Backward-compatible shim around :mod:`vectra_artifacts.compilers`.

Pre-existing callers (``tsvc_2/compile_cpp_kernels.py``,
``tsvc_2/compile_dace_kernels.py``) import ``CXX``, ``COMPILE_FLAGS``,
``LINK_FLAGS``, ``configure_dace`` from here. We now resolve those
values from the env-var trio set by ``vectra-source-sh`` (or any
``source.sh`` written by :func:`vectra_artifacts.compilers.write_source_sh`):

* ``CXX_COMPILER``  -- ``clang`` | ``gcc`` | ``icpx``  (default ``gcc``).
* ``CXX_COSTMODEL`` -- ``default`` | ``cheap`` | ``no``  (default ``default``).
* ``CXX_MATH``      -- ``0`` | ``1``                     (default ``0``).
* ``CPU_NAME``      -- target CPU SKU                    (default ``""`` -> probe local).
* ``EXTRA_FLAGS``   -- caller-supplied extras appended verbatim          (optional).
* ``CXX``           -- override the resolved executable                  (optional).

When none of these are set, the resolved set is the same baseline the
legacy ``compiler_config.py`` shipped (``-O3 -ffast-math
-fno-math-errno -fopenmp -fstrict-aliasing ...``), so existing scripts
keep working unchanged.

Prefer importing directly from :mod:`vectra_artifacts.compilers` in new
code.
"""
import os

from vectra_artifacts.compilers import (Compiler, CostModel, configure_dace as _configure_dace, get_flags)
from vectra_artifacts.compilers.flags import LINK_BASE_FLAGS

_COMPILER_BY_NAME = {c.value: c for c in Compiler}
_COSTMODEL_BY_NAME = {c.value: c for c in CostModel}


def _resolve():
    comp_name = os.environ.get("CXX_COMPILER", "gcc")
    cm_name = os.environ.get("CXX_COSTMODEL", "default")
    math = os.environ.get("CXX_MATH", "0") == "1"
    cpu = os.environ.get("CPU_NAME") or None

    compiler = _COMPILER_BY_NAME.get(comp_name, Compiler.GCC)
    cost_model = _COSTMODEL_BY_NAME.get(cm_name, CostModel.DEFAULT)

    fs = get_flags(compiler, cost_model, math=math, cpu=cpu)
    return fs


_FLAG_SET = _resolve()

#: Compiler executable. ``CXX`` env var overrides the resolved default.
CXX: str = os.environ.get("CXX") or _FLAG_SET.compiler.executable()

#: Compile flags. Extra space-separated tokens via ``EXTRA_FLAGS`` env
#: var are appended.
COMPILE_FLAGS = list(_FLAG_SET.compile_flags)
_EXTRA = os.environ.get("EXTRA_FLAGS", "")
if _EXTRA:
    # Only append tokens not already present to avoid duplication
    existing = set(COMPILE_FLAGS)
    for token in _EXTRA.split():
        if token not in existing:
            COMPILE_FLAGS.append(token)
            existing.add(token)

#: Link flags. ``LINK_FLAGS`` env var appends if set.
LINK_FLAGS = list(_FLAG_SET.link_flags)
_EXTRA_LINK = os.environ.get("LINK_FLAGS", "")
if _EXTRA_LINK:
    # LINK_FLAGS.extend(_EXTRA_LINK.split())
    # Only append tokens not already present to avoid duplication
    existing = set(LINK_FLAGS)
    for token in _EXTRA_LINK.split():
        if token not in existing:
            LINK_FLAGS.append(token)
            existing.add(token)


def configure_dace():
    """Apply the resolved (compiler, cost-model, math, cpu) to DaCe.

    Pre-existing callers call this with no arguments; we use the env
    vars to choose the right combination.
    """
    return _configure_dace(_FLAG_SET)


def resolved_flag_set():
    """Return the underlying :class:`FlagSet` for inspection / logging."""
    return _FLAG_SET


__all__ = [
    "CXX",
    "COMPILE_FLAGS",
    "LINK_FLAGS",
    "configure_dace",
    "resolved_flag_set",
]
