#!/usr/bin/env python3
"""Thin entry point: compile every ``tsvc_2`` DaCe kernel.

Defers to :func:`vectra_artifacts.corpus_build.compile_dace_all`.

Usage::

    python -m tsvc_2.compile_dace_kernels
"""
from vectra_artifacts.corpus_build import compile_dace_all as compile_all_dace_kernels
from vectra_artifacts.corpus_build import main_compile_dace


def main() -> int:
    return main_compile_dace(
        default_root="tsvc_2/tsvc_dace_microkernels",
        default_build_dir=".dace_build",
    )


if __name__ == "__main__":
    raise SystemExit(main())
