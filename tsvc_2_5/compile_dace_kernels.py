#!/usr/bin/env python3
"""Thin entry point: compile every ``tsvc_2_5`` DaCe kernel.

Defers to :func:`vectra_artifacts.corpus_build.compile_dace_all`. The
historical ``compile_all_dace_kernels`` name is re-exported so any
external caller using it keeps working.

Usage::

    python -m tsvc_2_5.compile_dace_kernels
"""
from vectra_artifacts.corpus_build import compile_dace_all as compile_all_dace_kernels
from vectra_artifacts.corpus_build import main_compile_dace


def main() -> int:
    return main_compile_dace(
        default_root="tsvc_2_5/tsvc_2_5_dace_microkernels",
        default_build_dir=".dace_ext_build",
    )


if __name__ == "__main__":
    raise SystemExit(main())
