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
    _KernelRow("wavefront2d", "wavefront skew (2D anti-diagonal)",
               "a[i,j] = 0.25*(a[i,j] + a[i-1,j] + a[i,j-1] + a[i-1,j-1])",
               "WavefrontSkew (i+j) before LoopToMap; both loops sequential as written"),
    _KernelRow("ext_break_find_first", "early-exit (guard before body)", "if d[i] < 0: break; a[i] += b[i]*c[i]",
               "EarlyExitToFindIndex: find-first min-reduce + clipped body Map"),
    _KernelRow("ext_break_post_body", "early-exit (guard after body)", "a[i] += b[i]*c[i]; if c[i] > b[i]: break",
               "find-first bound is inclusive; breaking iteration's write retained"),
    _KernelRow("ext_break_capture", "early-exit with index/value capture",
               "if a[i] > K: out_index=i; out_value=a[i]; break", "argmin-of-index reconstruction at the exit edge"),
    _KernelRow("cond_reduce_sum", "conditional reduction (positive)", "if a[i] > 0: out += a[i]",
               "LoopToConditionalReduce masks addend with 0 then WCR-on-scalar"),
    _KernelRow("cond_reduce_sym", "conditional reduction (symbolic threshold)", "if a[i] > K: out += a[i]",
               "symbolic predicate computed at runtime before the WCR reduction"),
    _KernelRow("iv_additive", "additive induction variable", "s = 0; for i: s += 1.5; out = s",
               "InductionVariableSubstitution closed form s = 1.5 * LEN_1D (O(N)->O(1))"),
    _KernelRow("iv_multiplicative", "multiplicative induction variable", "s = 1; for i: s *= 0.99; out = s",
               "geometric-product closed form s = 0.99 ** LEN_1D"),
    _KernelRow("argmax_value", "argmax value reduction", "x = a[0]; for i: if a[i] > x: x = a[i]",
               "ArgMaxLift to Reduce(Max) libnode"),
    _KernelRow("argmin_value", "argmin value reduction", "x = a[0]; for i: if a[i] < x: x = a[i]",
               "ArgMaxLift to Reduce(Min) libnode"),
    _KernelRow("neg_stride_rev", "negative-stride reverse loop", "for i in range(N-1, -1, -1): a[i] = b[i] + 1",
               "NormalizeNegativeStride to positive form before LoopToMap"),
    _KernelRow("reroll_saxpy7", "manually-unrolled saxpy (7x, prime)", "step-7 loop, 7 lanes a[i+k] += b[i+k]*2",
               "prime unroll factor never tiles a vector width; RerollUnrolledLoops to unit-step before LoopToMap"),
    _KernelRow("scan_strided_2", "strided prefix scan (stride 2)", "a[i] = a[i-2] + x[i]",
               "LoopToScan emits two Scans (even/odd residue classes)"),
    _KernelRow("scan_strided_sym", "strided prefix scan (symbolic stride)", "a[i] = a[i-K] + x[i]",
               "K residue classes -> stride-K vector Scan; Scan count is a runtime symbol"),
    _KernelRow("scan_multi_carry", "two scans in one body (add + mul)", "a[i]=a[i-1]+x[i]; b[i]=b[i-1]*y[i]",
               "LoopToScan emits two Scans with different operators"),
    _KernelRow("scan_conditional", "masked prefix scan", "if mask[i]>0: out[i]=out[i-1]+delta[i] else out[i-1]",
               "LoopToScan descends into ConditionalBlock; false branch = additive identity"),
    _KernelRow("scan_multi_5carry", "five parallel scans (cloudsc pfsqrf)", "acc[r,i]=acc[r,i-1]+delta[r,i], r=0..4",
               "LoopToScan matches five independent carries -> five Scans / one vector Scan"),
    _KernelRow("argmax_with_index", "argmax with index capture", "if a[i]>x: x=a[i]; idx=i",
               "ArgMaxLift two-accumulator (value + index) variant (s315)"),
    _KernelRow("reroll_gather", "manually-unrolled gather saxpy (7x)", "step-7 loop, 7 lanes a[i+k]+=b[ip[i+k]]*2",
               "RerollUnrolledLoops + data-dependent gather; prime unroll (s353)"),
    _KernelRow("thomas_solve", "tridiagonal Thomas (two-sweep)", "forward elim then backward subst on same axis",
               "two sequential recurrences, second descending and reading the first's results"),
    _KernelRow("reduce_inner_carry", "outer-parallel inner-carried reduction", "for i (par): for j: s+=a[i,j]; out[i]=s",
               "outer i -> Map, inner j -> sequential reduction / per-row Reduce"),
    _KernelRow("config_select_branch", "config-flag branch select (if inside)", "if K>0: out_a[i]=.. else out_b[i]=..",
               "MoveLoopInvariantIfUp hoists the invariant guard out, splitting into two parallel Maps"),
    _KernelRow("move_if_data_dep_nest", "data-dep guard mid-nest (move if in)",
               "for i: if cond[i]>0: for j: out[i,j]=src[i,j]*2",
               "MoveIfIntoLoop pushes the guard innermost -> 2D parallel Map (GPU grid)"),
    _KernelRow("fuse_move_ifs", "two guarded nests fuse after move-if-in",
               "for i: if cond[i]: for j: a..  ;  if K: for i,j: b..",
               "move both guards innermost -> identical nests fuse into one parallel Map"),
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
