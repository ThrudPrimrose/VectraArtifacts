#!/usr/bin/env python3
"""Thin entry point: split ``tsvc_2_5_core.cpp`` into per-kernel files.

Defers to :func:`vectra_artifacts.corpus_build.split_cpp` (shared with
:mod:`tsvc_2`) so the splitter has exactly one implementation.

Usage::

    python -m tsvc_2_5.split_cpp_kernels
    # or with overrides:
    python tsvc_2_5/split_cpp_kernels.py -i <core.cpp> -o <out-dir>
"""
from vectra_artifacts.corpus_build import main_split_cpp


def main() -> int:
    return main_split_cpp(
        default_input="tsvc_2_5/tsvc_2_5_core.cpp",
        default_out_dir="tsvc_2_5/tsvc_2_5_cpp_microkernels",
    )


if __name__ == "__main__":
    raise SystemExit(main())
