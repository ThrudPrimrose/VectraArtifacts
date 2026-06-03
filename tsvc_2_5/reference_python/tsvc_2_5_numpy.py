# Copyright 2019-2026 ETH Zurich and the DaCe authors. All rights reserved.
"""Numpy oracles for ``tsvc_2_5_core``.

One function per kernel, taking the same arguments as the DaCe / C++
counterpart (input arrays in, output arrays in-place). Used by the
correctness harness to verify the compiled kernel output.
"""
import numpy as np


def ref_strided_load_ssym(dst: np.ndarray, src: np.ndarray, scale: float, ssym: int) -> None:
    n = dst.shape[0]
    for i in range(n):
        dst[i] = src[i * ssym] * scale


def ref_strided_load_2(dst: np.ndarray, src: np.ndarray, scale: float) -> None:
    n = dst.shape[0]
    for i in range(n):
        dst[i] = src[i * 2] * scale


def ref_strided_store_ssym(dst: np.ndarray, src: np.ndarray, scale: float, ssym: int) -> None:
    n = src.shape[0]
    for i in range(n):
        dst[i * ssym] = src[i] * scale


def ref_strided_store_2(dst: np.ndarray, src: np.ndarray, scale: float) -> None:
    n = src.shape[0]
    for i in range(n):
        dst[i * 2] = src[i] * scale


def ref_gather_load(dst: np.ndarray, src: np.ndarray, idx: np.ndarray, scale: float) -> None:
    n = dst.shape[0]
    for i in range(n):
        dst[i] = src[idx[i]] * scale


def ref_scatter_store(dst: np.ndarray, src: np.ndarray, idx: np.ndarray, scale: float) -> None:
    n = src.shape[0]
    for i in range(n):
        dst[idx[i]] = src[i] * scale


def ref_floordiv_offset(a: np.ndarray, b: np.ndarray) -> None:
    n = a.shape[0]
    half = n // 2
    for i in range(half):
        a[i] = a[i + half] + b[i]


def ref_floordiv_offset_m(a: np.ndarray, b: np.ndarray, m: int) -> None:
    n = a.shape[0]
    chunk = n // m
    for i in range(chunk):
        a[i] = a[i + chunk] + b[i]


def ref_modular_wrap(a: np.ndarray, b: np.ndarray, k: int) -> None:
    n = a.shape[0]
    for i in range(n):
        a[(i + k) % n] = b[i]


def ref_war_unit(a: np.ndarray, b: np.ndarray) -> None:
    n = a.shape[0]
    for i in range(n - 1):
        a[i] = a[i + 1] + b[i]


def ref_war_sym(a: np.ndarray, b: np.ndarray, k: int) -> None:
    n = a.shape[0]
    for i in range(n - k):
        a[i] = a[i + k] + b[i]


def ref_peel_multi_back(a: np.ndarray, b: np.ndarray) -> None:
    n = a.shape[0]
    for i in range(n):
        a[i] = b[i] * 2.0
        if i == n - 1:
            a[n - 2] = a[n - 2] + 1.0
        elif i == n - 2:
            a[n - 3] = a[n - 3] + 1.0


def ref_tile_2d_sym(b: np.ndarray, a: np.ndarray, s: int) -> None:
    n = a.shape[0]  # assume square
    for ti in range(0, n, s):
        for tj in range(0, n, s):
            for i in range(ti, ti + s):
                for j in range(tj, tj + s):
                    b[i, j] = a[i, j] * 2.0


# TSVC-named symbolic-step variants


def ref_s121_sym_k(a: np.ndarray, b: np.ndarray, k: int) -> None:
    """TSVC s121 with symbolic offset ``k``: ``a[i] = a[i+k] + b[i]``."""
    n = a.shape[0]
    for i in range(n - k):
        a[i] = a[i + k] + b[i]


def ref_s4113_ssym(a: np.ndarray, b: np.ndarray, c: np.ndarray, ip: np.ndarray, ssym: int) -> None:
    """TSVC s4113 with strided index access:
    ``a[ip[i*ssym]] = b[ip[i*ssym]] + c[i]``."""
    n = a.shape[0]
    for i in range(n // ssym):
        a[ip[i * ssym]] = b[ip[i * ssym]] + c[i]


def ref_vas_ssym(a: np.ndarray, b: np.ndarray, ip: np.ndarray, ssym: int) -> None:
    """TSVC vas with strided index scatter: ``a[ip[i*ssym]] = b[i]``."""
    n = a.shape[0]
    for i in range(n // ssym):
        a[ip[i * ssym]] = b[i]


# Loop-fission family


def ref_fission_indep_2body(a: np.ndarray, b: np.ndarray, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> None:
    """Two independent writes sharing three reads."""
    n = a.shape[0]
    for i in range(n):
        a[i] = x[i] * y[i] + z[i]
        b[i] = x[i] - y[i] * z[i]


def ref_fission_dep_then_indep(a: np.ndarray, b: np.ndarray, x: np.ndarray, y: np.ndarray) -> None:
    """Body A unit-offset carried dep, body B independent."""
    n = a.shape[0]
    a[0] = x[0]
    for i in range(1, n):
        a[i] = a[i - 1] + x[i]
        b[i] = y[i] * 2.0


def ref_fission_dep_const_offset(a: np.ndarray, b: np.ndarray, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> None:
    """Body A offset-2 carried dep, body B independent."""
    n = a.shape[0]
    a[0] = x[0]
    a[1] = x[1]
    for i in range(2, n):
        a[i] = a[i - 2] + x[i]
        b[i] = y[i] * z[i]


def ref_fission_dep_sym_offset(a: np.ndarray, b: np.ndarray, x: np.ndarray, y: np.ndarray, z: np.ndarray,
                               k: int) -> None:
    """Body A symbolic-offset (``k``) carried dep, body B independent.
    Caller must initialize ``a[0..k-1]``."""
    n = a.shape[0]
    for i in range(k, n):
        a[i] = a[i - k] + x[i]
        b[i] = y[i] * z[i]


# Already-tiled stencils


def _jacobi2d_tiled(b: np.ndarray, a: np.ndarray, t: int) -> None:
    n = a.shape[0]
    for ii in range(1, n - 1 - t, t):
        for jj in range(1, n - 1 - t, t):
            for i in range(ii, ii + t):
                for j in range(jj, jj + t):
                    b[i, j] = 0.2 * (a[i, j] + a[i - 1, j] + a[i + 1, j] + a[i, j - 1] + a[i, j + 1])


def ref_jacobi2d_tiled_const(b: np.ndarray, a: np.ndarray) -> None:
    """2D Jacobi 5-point stencil pre-tiled with constant tile size 64."""
    _jacobi2d_tiled(b, a, 64)


def ref_jacobi2d_tiled_sym(b: np.ndarray, a: np.ndarray, t: int) -> None:
    """2D Jacobi 5-point stencil pre-tiled with symbolic tile size ``t``."""
    _jacobi2d_tiled(b, a, t)


def _jacobi2d_double_tiled(b: np.ndarray, a: np.ndarray, t1: int, t2: int) -> None:
    n = a.shape[0]
    for ii in range(1, n - 1 - t1, t1):
        for jj in range(1, n - 1 - t1, t1):
            for iii in range(ii, ii + t1, t2):
                for jjj in range(jj, jj + t1, t2):
                    for i in range(iii, iii + t2):
                        for j in range(jjj, jjj + t2):
                            b[i, j] = 0.2 * (a[i, j] + a[i - 1, j] + a[i + 1, j] + a[i, j - 1] + a[i, j + 1])


def ref_jacobi2d_double_tiled_const(b: np.ndarray, a: np.ndarray) -> None:
    """2D Jacobi 5-point stencil pre-tiled with constant outer (64) and inner (8) tiles."""
    _jacobi2d_double_tiled(b, a, 64, 8)


def ref_jacobi2d_double_tiled_sym(b: np.ndarray, a: np.ndarray, t1: int, t2: int) -> None:
    """Two-level Jacobi tiling with symbolic outer ``t1`` and inner ``t2``."""
    _jacobi2d_double_tiled(b, a, t1, t2)


def _heat3d_tiled(b: np.ndarray, a: np.ndarray, t: int) -> None:
    n = a.shape[0]
    for kk in range(1, n - 1 - t, t):
        for jj in range(1, n - 1 - t, t):
            for ii in range(1, n - 1 - t, t):
                for k in range(kk, kk + t):
                    for j in range(jj, jj + t):
                        for i in range(ii, ii + t):
                            b[k, j, i] = (0.125 * (a[k + 1, j, i] - 2.0 * a[k, j, i] + a[k - 1, j, i]) + 0.125 *
                                          (a[k, j + 1, i] - 2.0 * a[k, j, i] + a[k, j - 1, i]) + 0.125 *
                                          (a[k, j, i + 1] - 2.0 * a[k, j, i] + a[k, j, i - 1]) + a[k, j, i])


def ref_heat3d_tiled_const(b: np.ndarray, a: np.ndarray) -> None:
    """3D 7-point heat stencil pre-tiled with constant tile size 8."""
    _heat3d_tiled(b, a, 8)


def ref_heat3d_tiled_sym(b: np.ndarray, a: np.ndarray, t: int) -> None:
    """3D 7-point heat stencil pre-tiled with symbolic tile size ``t``."""
    _heat3d_tiled(b, a, t)


# ECRAD-style clamped reduction


def ref_ecrad_clamped_reduction(out: np.ndarray, x: np.ndarray, y: np.ndarray, d: np.ndarray) -> None:
    """clamp(exp(-sqrt(max(x*x+y*y, 1e-12)) * d), 0, 1)."""
    n = out.shape[0]
    for i in range(n):
        k_val = np.sqrt(max(x[i] * x[i] + y[i] * y[i], 1e-12))
        e = np.exp(-k_val * d[i])
        out[i] = max(0.0, min(e, 1.0))


# Masked stores


def ref_masked_store_const(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> None:
    """Predicated store: ``if mask[i] > 0: a[i] = b[i]``."""
    n = a.shape[0]
    for i in range(n):
        if mask[i] > 0:
            a[i] = b[i]


def ref_masked_store_sym(a: np.ndarray, b: np.ndarray, threshold_data: np.ndarray, k: float) -> None:
    """Predicated store: ``if threshold_data[i] > k: a[i] = b[i]``."""
    n = a.shape[0]
    for i in range(n):
        if threshold_data[i] > k:
            a[i] = b[i]


# ---------------------------------------------------------------------------
#  Quasi-affine subscript / iteration patterns
# ---------------------------------------------------------------------------


def ref_quasi_affine_reduce_even(a: np.ndarray, out: np.ndarray) -> None:
    """``out[0] = sum(a[0::2])`` (stride-2 reduction from index 0)."""
    out[0] = float(a[0::2].sum())


def ref_quasi_affine_reduce_odd(a: np.ndarray, out: np.ndarray) -> None:
    """``out[0] = sum(a[1::2])`` (stride-2 reduction from index 1)."""
    out[0] = float(a[1::2].sum())


def ref_quasi_affine_pairwise_sum(a: np.ndarray, b: np.ndarray) -> None:
    """``b[i] = a[2*i] + a[2*i + 1]`` -- pairwise gather + add."""
    n = b.shape[0]
    b[:] = a[0:2 * n:2] + a[1:2 * n:2]


def ref_quasi_affine_mod_k_stripe(a: np.ndarray, b: np.ndarray, c: np.ndarray, k: int) -> None:
    """``a[i] = b[i] * 2.0 if i % k == 0 else c[i]`` -- mod-k stripe."""
    n = a.shape[0]
    idx = np.arange(n)
    mask = (idx % k) == 0
    a[mask] = b[mask] * 2.0
    a[~mask] = c[~mask]


def ref_quasi_affine_floor_div_scatter(a: np.ndarray, b: np.ndarray) -> None:
    """``b[i // 2] += a[i]`` -- pair-stripe reduction. The numpy
    oracle uses ``np.add.at`` for the unbuffered scatter so each pair
    of source indices accumulates into the same output cell."""
    n2 = a.shape[0]
    idx = np.arange(n2) // 2
    np.add.at(b, idx, a)
