#!/usr/bin/env python3
"""Thin entry point: compile + link ``tsvc_2_5`` cpp microkernels.

Defers to :func:`vectra_artifacts.corpus_build.compile_cpp_library` /
:func:`load_cpp_library` so the build pipeline has exactly one
implementation. Re-exports them at module scope so call sites using
the historical names (``compile_library`` / ``load_library``) keep
working.

Usage::

    python -m tsvc_2_5.compile_cpp_kernels
"""
from vectra_artifacts.corpus_build import compile_cpp_library as compile_library
from vectra_artifacts.corpus_build import load_cpp_library as load_library
from vectra_artifacts.corpus_build import main_compile_cpp


def main() -> int:
    return main_compile_cpp(
        default_root="tsvc_2_5/tsvc_2_5_cpp_microkernels",
        default_build_dir=".tsvc_ext_build",
        default_so_name="libtsvc_extensions_kernels.so",
    )


if __name__ == "__main__":
    raise SystemExit(main())
