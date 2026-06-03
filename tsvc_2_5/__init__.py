"""TSVC-2.5 extension corpus: kernels exercising symbolic-step,
symbolic-offset, and quasi-affine patterns where polyhedral tools
fail.

Public API:

* :func:`kernel_table` -- iterate kernel metadata (name, short
  description, blocking factor).
* :data:`ALL_KERNELS` -- list of kernel-name strings, in declaration
  order.
* :class:`ExtensionLibrary` -- lazy ctypes loader for the per-kernel
  C++ shared library (auto-runs split + compile when missing).

The corpus mirrors :mod:`tsvc_2`'s build pipeline:

============================  =================================================
Script                        Output
============================  =================================================
``split_cpp_kernels.py``      ``tsvc_2_5_cpp_microkernels/<kernel>/<kernel>_{d,f}.cpp``
``split_dace_kernels.py``     ``tsvc_2_5_dace_microkernels/<kernel>/<kernel>_{d,f}.py``
``compile_cpp_kernels.py``    ``.tsvc_ext_build/libtsvc_extensions_kernels.so``
``compile_dace_kernels.py``   per-kernel SDFG ``.so`` under ``.dace_ext_build/``
============================  =================================================
"""
from typing import Iterator, NamedTuple


class _KernelRow(NamedTuple):
    name: str
    category: str
    description: str
    blocking_factor: str


_ROWS = [
    _KernelRow("ext_strided_load_ssym", "symbolic-stride load", "dst[i] = src[i * SSYM] * scale",
               "symbolic stride disables contig-load proof"),
    _KernelRow("ext_strided_load_2", "constant-stride load", "dst[i] = src[i * 2] * scale",
               "needs gather intrinsic for vectorization"),
    _KernelRow("ext_strided_store_ssym", "symbolic-stride store", "dst[i * SSYM] = src[i] * scale",
               "symbolic stride may collide; needs runtime guard"),
    _KernelRow("ext_strided_store_2", "constant-stride store", "dst[i * 2] = src[i] * scale",
               "needs scatter intrinsic"),
    _KernelRow("ext_gather_load", "indirect gather", "dst[i] = src[idx[i]] * scale",
               "data-dependent read; gather intrinsic"),
    _KernelRow("ext_scatter_store", "indirect scatter", "dst[idx[i]] = src[i] * scale",
               "permutation proof required for safe lift"),
    _KernelRow("ext_floordiv_offset", "quasi-affine floor-div offset", "a[i] = a[i + LEN_1D // 2] + b[i]",
               "Pluto refuses floor-div in dep vector"),
    _KernelRow("ext_floordiv_offset_m", "quasi-affine floor-div with symbol", "a[i] = a[i + LEN_1D // M] + b[i]",
               "symbolic divisor compounds the floor-div"),
    _KernelRow("ext_modular_wrap", "modulo wraparound", "a[(i + K) % LEN_1D] = b[i]",
               "peel_limit knob unlocks parallelization"),
    _KernelRow("ext_war_unit", "unit-offset WAR", "a[i] = a[i + 1] + b[i]",
               "break_anti_dependence knob snapshot-renames"),
    _KernelRow("ext_war_sym", "symbolic-offset WAR", "a[i] = a[i + K] + b[i]", "snapshot-rename + symbolic K guard"),
    _KernelRow("ext_peel_multi_back", "multi-front conflict peel",
               "if i == N-1: tail-write 1 elif i == N-2: tail-write 2", "peel_limit >= 2 required"),
    _KernelRow("ext_tile_2d_sym", "2D tile with symbolic tile size", "for ti / tj / i / j with tile size S",
               "untile fixpoint + multi-dim ascent"),
    _KernelRow("s121_sym_k", "TSVC s121 with symbolic offset", "a[i] = a[i + K] + b[i]",
               "snapshot-rename + K > 0 runtime guard"),
    _KernelRow("s4113_ssym", "TSVC s4113 with strided index access", "a[ip[i*SSYM]] = b[ip[i*SSYM]] + c[i]",
               "permutation proof breaks under symbolic stride"),
    _KernelRow("vas_ssym", "TSVC vas with strided index scatter", "a[ip[i*SSYM]] = b[i]",
               "ScatterToGuardedMaps sort+dup-count guard needed"),
    _KernelRow("fission_indep_2body", "fission (two independent bodies)", "a[i] = x*y+z; b[i] = x-y*z",
               "fission yields two independent vector loops under register pressure"),
    _KernelRow("fission_dep_then_indep", "fission (carried-dep + independent)",
               "a[i] = a[i-1] + x[i]; b[i] = y[i] * 2.0", "fission required so independent body vectorizes"),
    _KernelRow("fission_dep_const_offset", "fission (constant-offset-2 dep + independent)",
               "a[i] = a[i-2] + x[i]; b[i] = y[i] * z[i]", "fission separates offset-2 dep body from independent body"),
    _KernelRow("fission_dep_sym_offset", "fission (symbolic-offset dep + independent)",
               "a[i] = a[i-K] + x[i]; b[i] = y[i] * z[i]",
               "symbolic-offset carried dep + independent body; fission required"),
    _KernelRow("jacobi2d_tiled_const", "pre-tiled 2D Jacobi (constant tile)", "5-point stencil pre-tiled with T=64",
               "tile-untile + multi-dim ascent anchor (constant tile)"),
    _KernelRow("jacobi2d_tiled_sym", "pre-tiled 2D Jacobi (symbolic tile)", "5-point stencil pre-tiled with symbolic T",
               "tile-untile + multi-dim ascent anchor (symbolic tile)"),
    _KernelRow("jacobi2d_double_tiled_const", "pre-tiled 2D Jacobi (two constant levels)",
               "5-point stencil pre-tiled with T1=64, T2=8", "two-level untile pass anchor"),
    _KernelRow("jacobi2d_double_tiled_sym", "pre-tiled 2D Jacobi (two symbolic levels)",
               "5-point stencil pre-tiled with symbolic T1, T2", "two-level untile + symbolic tile sizes"),
    _KernelRow("heat3d_tiled_const", "pre-tiled 3D heat (constant tile)", "7-point heat stencil pre-tiled with T=8",
               "3D tile-untile + multi-dim ascent (constant tile)"),
    _KernelRow("heat3d_tiled_sym", "pre-tiled 3D heat (symbolic tile)",
               "7-point heat stencil pre-tiled with symbolic T", "3D tile-untile + multi-dim ascent (symbolic tile)"),
    _KernelRow("ecrad_clamped_reduction", "ECRAD-style clamped reduction",
               "out[i] = clamp(exp(-sqrt(max(x*x+y*y, eps)) * d), 0, 1)",
               "transcendental + min/max clamps; SLEEF / libmvec intrinsic lowering"),
    _KernelRow("masked_store_const", "predicated store (int mask)", "if mask[i] > 0: a[i] = b[i]",
               "masked-store / blend-store vector intrinsic required"),
    _KernelRow("masked_store_sym", "predicated store (symbolic threshold)", "if threshold_data[i] > K: a[i] = b[i]",
               "masked-store with symbolic-scalar comparison"),
    _KernelRow("quasi_affine_reduce_even", "quasi-affine stride-2 reduction (even)", "out[0] = sum(a[0::2])",
               "stride-2 subset; needs contig proof on a[2*i]"),
    _KernelRow("quasi_affine_reduce_odd", "quasi-affine stride-2 reduction (odd)", "out[0] = sum(a[1::2])",
               "non-zero starting offset extends the canonicalize hop"),
    _KernelRow("quasi_affine_pairwise_sum", "quasi-affine pairwise gather", "b[i] = a[2*i] + a[2*i + 1]",
               "deinterleave-load opportunity that both compilers often miss"),
    _KernelRow("quasi_affine_mod_k_stripe", "quasi-affine mod-K stripe", "a[i] = b[i]*2 if i % K == 0 else c[i]",
               "masked-store with symbolic-divisor predicate"),
    _KernelRow("quasi_affine_floor_div_scatter", "quasi-affine floor-div scatter", "b[i // 2] += a[i]",
               "pair-stripe reduction; cannot vectorize naively"),
]

ALL_KERNELS = tuple(r.name for r in _ROWS)


def kernel_table() -> Iterator[_KernelRow]:
    """Yield one :class:`_KernelRow` per kernel."""
    yield from _ROWS


def __getattr__(name):
    """Lazy re-export of :class:`ExtensionLibrary` so that simply
    importing :mod:`tsvc_2_5` does not pull in the ctypes
    machinery (and the .so build) when callers only want the metadata
    table."""
    if name == "ExtensionLibrary":
        from .tsvc_2_5_bindings import ExtensionLibrary
        return ExtensionLibrary
    raise AttributeError(f"module 'tsvc_2_5' has no attribute {name!r}")


__all__ = ("ALL_KERNELS", "kernel_table", "ExtensionLibrary")
