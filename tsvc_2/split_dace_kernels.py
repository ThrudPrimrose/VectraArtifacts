#!/usr/bin/env python3
"""Thin entry point: split ``tsvc2_core.py`` into per-kernel files.

Defers to :func:`vectra_artifacts.corpus_build.split_dace`. TSVC-2
kernels are decorated as ``dace_<name>`` (so we strip ``"dace_"``)
and carry an outer ``for nl in range(ITERATIONS)`` loop, so
``emit_single=True`` also writes the ``_d_single`` / ``_f_single``
siblings the benchmark grid uses.

Usage::

    python -m tsvc_2.split_dace_kernels
"""
from vectra_artifacts.corpus_build import main_split_dace


def main() -> int:
    return main_split_dace(
        default_input="tsvc_2/tsvc2_core.py",
        default_out_dir="tsvc_2/tsvc_dace_microkernels",
        source_prefix="dace_",
        emit_single=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
