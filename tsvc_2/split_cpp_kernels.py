#!/usr/bin/env python3
"""Thin entry point: split ``tsvc2_core.cpp`` into per-kernel files.

Defers to :func:`vectra_artifacts.corpus_build.split_cpp` (shared with
:mod:`tsvc_2_5`) so the splitter has exactly one implementation. TSVC-2
kernels carry an outer ``for (int nl = 0; ...; nl++)`` repeat loop, so
``emit_single=True`` also writes the ``_d_single`` / ``_f_single``
siblings -- matching the DaCe corpus's ``_single`` variants.

Usage::

    python -m tsvc_2.split_cpp_kernels
"""
from vectra_artifacts.corpus_build import main_split_cpp


def main() -> int:
    return main_split_cpp(
        default_input="tsvc_2/tsvc2_core.cpp",
        default_out_dir="tsvc_2/tsvc_cpp_microkernels",
        emit_single=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
