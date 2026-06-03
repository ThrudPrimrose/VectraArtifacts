#!/usr/bin/env python3
"""Thin entry point: compile + link ``tsvc_2`` cpp microkernels.

Defers to :func:`vectra_artifacts.corpus_build.compile_cpp_library` /
:func:`load_cpp_library`. Re-exports them under the historical names
so ``tsvc_2/tsvc_bindings.py``'s auto-build path keeps working.

Usage::

    python -m tsvc_2.compile_cpp_kernels
"""
from vectra_artifacts.corpus_build import compile_cpp_library as compile_library
from vectra_artifacts.corpus_build import load_cpp_library as load_library
from vectra_artifacts.corpus_build import main_compile_cpp


def main() -> int:
    return main_compile_cpp(
        default_root="tsvc_2/tsvc_cpp_microkernels",
        default_build_dir=".tsvc_build",
        default_so_name="libtsvc_kernels.so",
    )


if __name__ == "__main__":
    raise SystemExit(main())
