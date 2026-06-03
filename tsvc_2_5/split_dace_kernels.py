#!/usr/bin/env python3
"""Thin entry point: split ``tsvc_2_5_core.py`` into per-kernel files.

Defers to :func:`vectra_artifacts.corpus_build.split_dace`. The
extension corpus uses bare kernel names (no ``dace_`` prefix) and has
no outer iteration loop, so we set ``emit_single=False``.

Usage::

    python -m tsvc_2_5.split_dace_kernels
"""
from vectra_artifacts.corpus_build import main_split_dace


def main() -> int:
    return main_split_dace(
        default_input="tsvc_2_5/tsvc_2_5_core.py",
        default_out_dir="tsvc_2_5/tsvc_2_5_dace_microkernels",
        source_prefix="",
        emit_single=False,
    )


if __name__ == "__main__":
    raise SystemExit(main())
