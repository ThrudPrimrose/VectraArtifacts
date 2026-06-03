"""Smoke tests for the ``tsvc_2_5`` corpus:

* Every listed kernel's ``@dace.program`` parses + builds an SDFG.
* The corpus seeds cleanly into the ``kernels`` table.
* Numpy oracle is callable with the documented signature on a small input.
"""
import importlib

import numpy as np
import pytest

from vectra_artifacts.database import Suite, connect, create_schema
from vectra_artifacts.database.queries import kernel_audit_rows

dace = pytest.importorskip("dace")
_core = pytest.importorskip("tsvc_2_5.tsvc_2_5_core")
_seed = importlib.import_module("vectra_artifacts.tsvc_audit").seed_tsvc_2_5
_table = importlib.import_module("tsvc_2_5").kernel_table
_numpy = importlib.import_module("tsvc_2_5.reference_python.tsvc_2_5_numpy")


def test_every_listed_kernel_resolves():
    """Every name in ``ALL_KERNELS`` must be a real ``@dace.program``
    in ``tsvc_2_5_core``."""
    for row in _table():
        prog = getattr(_core, row.name, None)
        assert prog is not None, f'{row.name} missing from tsvc_2_5_core'
        assert hasattr(prog, "to_sdfg"), f'{row.name} is not a @dace.program'


@pytest.mark.parametrize("name", [r.name for r in _table()])
def test_kernel_builds_sdfg(name):
    """Each kernel must parse cleanly to an SDFG (we don't compile --
    that's the bench's job)."""
    prog = getattr(_core, name)
    sdfg = prog.to_sdfg(simplify=False)
    assert sdfg is not None


def test_seed_populates_extension_suite(tmp_path):
    db = tmp_path / "v.db"
    conn = connect(db)
    create_schema(conn)
    n = _seed(conn)
    assert n > 0
    rows = kernel_audit_rows(conn, suites=[Suite.TSVC_2_5])
    names = {r["name"] for r in rows}
    for row in _table():
        assert row.name in names


def test_numpy_oracle_war_unit_matches_python():
    """Spot-check one oracle: the ``s121`` shape."""
    rng = np.random.default_rng(0)
    a = rng.standard_normal(16)
    b = rng.standard_normal(16)
    ref = a.copy()
    _numpy.ref_war_unit(ref, b)
    expect = a.copy()
    for i in range(15):
        expect[i] = expect[i + 1] + b[i]
    assert np.allclose(ref, expect)


# -------------------------------------------------------------------------
#  End-to-end CPP-binding smoke (gated on a C++ compiler being available)
# -------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ext_library(tmp_path_factory):
    """Build and load ``libtsvc_extensions_kernels.so`` once per test
    module. Skips the smoke tests cleanly if no C++ toolchain is on
    PATH."""
    import shutil
    if shutil.which("g++") is None and shutil.which("clang++") is None:
        pytest.skip("no C++ compiler on PATH")

    from tsvc_2_5 import ExtensionLibrary
    build_dir = tmp_path_factory.mktemp("ext_build")
    so_path = build_dir / "libtsvc_extensions_kernels.so"
    return ExtensionLibrary(
        so_path=so_path,
        build_dir=build_dir,
        jobs=2,
    )


def test_binding_registers_all_kernels(ext_library):
    """Every name in the kernel table must surface in the loaded
    ``.so`` as a ``_d`` and ``_f`` symbol."""
    names = set(ext_library.list_kernels())
    for row in _table():
        assert f"{row.name}_d" in names, f"{row.name}_d not exposed"
        assert f"{row.name}_f" in names, f"{row.name}_f not exposed"


def test_ext_strided_load_2_matches_numpy_oracle(ext_library):
    n = 32
    src = np.arange(2 * n, dtype=np.float64) * 0.5 + 1.0
    dst = np.zeros(n, dtype=np.float64)
    elapsed_ns = ext_library.ext_strided_load_2_d(dst, src, scale=2.0, len_1d=n)
    assert elapsed_ns >= 0
    assert np.allclose(dst, src[::2] * 2.0)


def test_ext_strided_load_ssym_matches_numpy_oracle(ext_library):
    n, ssym = 32, 3
    src = np.arange(ssym * n, dtype=np.float64) * 0.25 + 1.0
    dst = np.zeros(n, dtype=np.float64)
    ext_library.ext_strided_load_ssym_d(dst, src, scale=2.0, len_1d=n, ssym=ssym)
    assert np.allclose(dst, src[::ssym] * 2.0)


def test_ext_gather_load_matches_numpy_oracle(ext_library):
    n = 32
    rng = np.random.default_rng(7)
    src = rng.standard_normal(n)
    idx = rng.permutation(n).astype(np.int64)
    dst = np.zeros(n, dtype=np.float64)
    ext_library.ext_gather_load_d(dst, src, idx, scale=0.5, len_1d=n)
    assert np.allclose(dst, src[idx] * 0.5)


def test_fp32_variant_runs(ext_library):
    n = 32
    src = np.arange(2 * n, dtype=np.float32) * 0.5
    dst = np.zeros(n, dtype=np.float32)
    ext_library.ext_strided_load_2_f(dst, src, scale=2.0, len_1d=n)
    assert np.allclose(dst, src[::2] * 2.0)


def test_fission_indep_2body_matches_numpy_oracle(ext_library):
    """Fission family: two independent writes share three reads."""
    n = 64
    rng = np.random.default_rng(11)
    x = rng.standard_normal(n)
    y = rng.standard_normal(n)
    z = rng.standard_normal(n)
    a = np.zeros(n, dtype=np.float64)
    b = np.zeros(n, dtype=np.float64)
    a_ref = a.copy()
    b_ref = b.copy()
    elapsed_ns = ext_library.fission_indep_2body_d(a, b, x, y, z, len_1d=n)
    assert elapsed_ns >= 0
    _numpy.ref_fission_indep_2body(a_ref, b_ref, x, y, z)
    assert np.allclose(a, a_ref)
    assert np.allclose(b, b_ref)


def test_jacobi2d_tiled_const_matches_numpy_oracle(ext_library):
    """Already-tiled stencil with constant tile size 64. ``len_2d`` must
    satisfy ``len_2d - 1 - 64`` being a positive multiple of 64 to walk
    at least one tile band."""
    n = 130  # gives one outer-tile iteration: range(1, 65, 64) -> [1]
    rng = np.random.default_rng(13)
    a = rng.standard_normal((n, n))
    b = np.zeros((n, n), dtype=np.float64)
    b_ref = np.zeros_like(b)
    elapsed_ns = ext_library.jacobi2d_tiled_const_d(b, a, len_2d=n)
    assert elapsed_ns >= 0
    _numpy.ref_jacobi2d_tiled_const(b_ref, a)
    assert np.allclose(b, b_ref)


def test_jacobi2d_tiled_sym_matches_numpy_oracle(ext_library):
    """Already-tiled stencil with symbolic tile size ``t``."""
    n = 66
    t = 16
    rng = np.random.default_rng(17)
    a = rng.standard_normal((n, n))
    b = np.zeros((n, n), dtype=np.float64)
    b_ref = np.zeros_like(b)
    elapsed_ns = ext_library.jacobi2d_tiled_sym_d(b, a, len_2d=n, t=t)
    assert elapsed_ns >= 0
    _numpy.ref_jacobi2d_tiled_sym(b_ref, a, t)
    assert np.allclose(b, b_ref)


def test_ecrad_clamped_reduction_matches_numpy_oracle(ext_library):
    """ECRAD-style clamped reduction: transcendental + min/max clamps."""
    n = 64
    rng = np.random.default_rng(19)
    x = rng.standard_normal(n)
    y = rng.standard_normal(n)
    d = np.abs(rng.standard_normal(n))
    out = np.zeros(n, dtype=np.float64)
    out_ref = np.zeros_like(out)
    elapsed_ns = ext_library.ecrad_clamped_reduction_d(out, x, y, d, len_1d=n)
    assert elapsed_ns >= 0
    _numpy.ref_ecrad_clamped_reduction(out_ref, x, y, d)
    assert np.allclose(out, out_ref, rtol=1e-12, atol=1e-12)
    assert np.all((out >= 0.0) & (out <= 1.0))


def test_quasi_affine_reduce_even_matches_numpy_oracle(ext_library):
    """Stride-2 reduction over even indices."""
    n = 32
    rng = np.random.default_rng(23)
    a = rng.standard_normal(n)
    out = np.zeros(1, dtype=np.float64)
    out_ref = np.zeros_like(out)
    ext_library.quasi_affine_reduce_even_d(a, out, len_1d=n)
    _numpy.ref_quasi_affine_reduce_even(a, out_ref)
    assert np.allclose(out, out_ref, rtol=1e-12)


def test_quasi_affine_pairwise_sum_matches_numpy_oracle(ext_library):
    """Pairwise gather: ``b[i] = a[2*i] + a[2*i + 1]``."""
    n = 32
    rng = np.random.default_rng(29)
    a = rng.standard_normal(2 * n)
    b = np.zeros(n, dtype=np.float64)
    b_ref = np.zeros_like(b)
    ext_library.quasi_affine_pairwise_sum_d(a, b, len_1d=n)
    _numpy.ref_quasi_affine_pairwise_sum(a, b_ref)
    assert np.allclose(b, b_ref)


def test_quasi_affine_floor_div_scatter_matches_numpy_oracle(ext_library):
    """Pair-stripe reduction: ``b[i // 2] += a[i]``. Output must be
    pre-zeroed; both source iterations land in the same dest cell."""
    n = 32
    rng = np.random.default_rng(31)
    a = rng.standard_normal(2 * n)
    b = np.zeros(n, dtype=np.float64)
    b_ref = np.zeros_like(b)
    ext_library.quasi_affine_floor_div_scatter_d(a, b, len_1d=n)
    _numpy.ref_quasi_affine_floor_div_scatter(a, b_ref)
    assert np.allclose(b, b_ref)


def test_quasi_affine_mod_k_stripe_matches_numpy_oracle(ext_library):
    """Mod-K stripe predicated assign."""
    n, k = 32, 4
    rng = np.random.default_rng(37)
    a = np.zeros(n, dtype=np.float64)
    b = rng.standard_normal(n)
    c = rng.standard_normal(n)
    a_ref = a.copy()
    ext_library.quasi_affine_mod_k_stripe_d(a, b, c, len_1d=n, k=k)
    _numpy.ref_quasi_affine_mod_k_stripe(a_ref, b, c, k)
    assert np.allclose(a, a_ref)
