"""Shared split + compile pipeline for the TSVC corpora.

Both ``tsvc_2`` and ``tsvc_2_5`` ship the same four scripts -- split a
monolithic core file into per-kernel sources, then compile them. The
historical implementation kept four 280-line scripts per corpus (eight
total) that diverged only in default paths. This module hoists the
shared logic so each corpus's scripts become thin entrypoints.

Public surface (all functions accept explicit paths so the corpus
scripts only set their own defaults):

* :func:`split_cpp` -- split ``<core>.cpp`` into ``<out>/<kernel>/<kernel>_{d,f}.cpp``.
* :func:`split_dace` -- split ``<core>.py`` into ``<out>/<kernel>/<kernel>_{d,f}.py``
                     (and ``_d_single`` / ``_f_single`` siblings when
                     the source carries an outer ``for nl in range(...)``
                     iteration loop, controlled by ``emit_single``).
* :func:`compile_cpp_library` -- compile every ``.cpp`` under a root
                                 into one shared library.
* :func:`compile_dace_all` -- compile every ``.py`` kernel under a root
                              via ``dace.SDFG.compile()``.
* :func:`load_cpp_library` -- ``ctypes.CDLL`` convenience wrapper
                              around :func:`compile_cpp_library`.

Each function has a small ``main_<name>(default_in, default_out)``
sibling that wires the same argparse the historical scripts used.
"""
from .split_cpp import split_cpp, main_split_cpp
from .split_dace import split_dace, main_split_dace
from .compile_cpp import compile_cpp_library, load_cpp_library, main_compile_cpp, parse_vec_reports
from .compile_dace import compile_dace_all, main_compile_dace, parse_dace_vec_reports

__all__ = [
    "split_cpp",
    "split_dace",
    "compile_cpp_library",
    "load_cpp_library",
    "parse_vec_reports",
    "parse_dace_vec_reports",
    "compile_dace_all",
    "main_split_cpp",
    "main_split_dace",
    "main_compile_cpp",
    "main_compile_dace",
]
