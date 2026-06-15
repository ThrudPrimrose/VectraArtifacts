"""Flag-matrix tests: every combo resolves to the expected delta."""
import pytest

from vectra_artifacts.compilers import Compiler, CostModel, get_flags, iter_combinations
from vectra_artifacts.compilers.flags import (BASELINE_FLAGS, LINK_BASE_FLAGS, vector_width_for_cpu)


def test_baseline_subset_of_default_flags():
    """Every baseline flag must appear in every (compiler, default) set."""
    for compiler in Compiler:
        fs = get_flags(compiler, CostModel.DEFAULT, cpu="intel_xeon")
        for f in BASELINE_FLAGS:
            assert f in fs.compile_flags, f"{compiler.value} default missing baseline {f}"
        assert "-march=native" in fs.compile_flags


def test_arm_omits_march_native():
    """`-march=native` is dropped for ARM cross-compiles."""
    fs = get_flags(Compiler.CLANG, CostModel.DEFAULT, cpu="arm")
    assert "-march=native" not in fs.compile_flags


@pytest.mark.parametrize("compiler,expected", [
    (Compiler.CLANG, "-fno-vectorize"),
    (Compiler.GCC,   "-fno-tree-vectorize"),
    (Compiler.ICPX,  "-no-vec"),
])
def test_disabled_costmodel_disables_vectorization(compiler, expected):
    fs = get_flags(compiler, CostModel.DISABLED)
    assert expected in fs.compile_flags


@pytest.mark.parametrize("compiler,expected", [
    (Compiler.CLANG, "-fno-slp-vectorize"),
    (Compiler.GCC,   "-fno-tree-slp-vectorize"),
    (Compiler.ICPX,  "-no-simd"),
])
def test_disabled_costmodel_also_disables_slp(compiler, expected):
    """DISABLED must kill both the loop vectoriser and the SLP vectoriser."""
    fs = get_flags(compiler, CostModel.DISABLED)
    assert expected in fs.compile_flags


@pytest.mark.parametrize("compiler,vec_flag,cost_flag", [
    (Compiler.CLANG, "-fvectorize",      "-fvect-cost-model=none"),
    (Compiler.GCC,   "-ftree-vectorize", "-fvect-cost-model=unlimited"),
    (Compiler.ICPX,  "-vec",             "-qopt-zmm-usage=high"),
])
def test_unlimited_costmodel_enables_aggressive_vectorization(compiler, vec_flag, cost_flag):


@pytest.mark.parametrize("cpu,width", [
    ("intel_xeon", 512),
    ("amd_epyc", 256),
    ("arm", 128),
    ("fugaku_a64fx", 512),
])
def test_vector_width_lookup_known_skus(cpu, width):
    assert vector_width_for_cpu(cpu) == width


def test_local_detect_returns_positive():
    """Probe must return a sane positive width on any host we care about.
    The fallback (256) keeps this true even on unknown CPUs."""
    from vectra_artifacts.compilers import detect_local_vector_width
    w = detect_local_vector_width()
    assert w in (128, 256, 512) or w > 0  # SVE can be any 128-bit multiple


def test_env_override_wins(monkeypatch):
    """``VEC_WIDTH=384`` (an unusual SVE value) must override every
    other source, including the fallback table."""
    monkeypatch.setenv("VEC_WIDTH", "384")
    assert vector_width_for_cpu("intel_xeon") == 384
    assert vector_width_for_cpu(None) == 384


def test_unknown_cpu_falls_back_to_default():
    assert vector_width_for_cpu("acme_42") == 256
    assert vector_width_for_cpu("acme_42", default=128) == 128


def test_clang_cheap_uses_width_hint_from_cpu():
    fs = get_flags(Compiler.CLANG, CostModel.CHEAP, cpu="intel_xeon")
    assert "-mprefer-vector-width=512" in fs.compile_flags
    fs = get_flags(Compiler.CLANG, CostModel.CHEAP, cpu="amd_epyc")
    assert "-mprefer-vector-width=256" in fs.compile_flags


def test_icpx_cheap_uses_qopt_flag():
    fs = get_flags(Compiler.ICPX, CostModel.CHEAP, cpu="intel_xeon")
    assert "-qopt-zmm-usage=high" in fs.compile_flags
    fs = get_flags(Compiler.ICPX, CostModel.CHEAP, cpu="amd_epyc")
    assert "-qopt-ymm-usage=high" in fs.compile_flags


def test_math_adds_libmvec_on_clang_only():
    fs = get_flags(Compiler.CLANG, CostModel.DEFAULT, math=True)
    assert "-fveclib=libmvec" in fs.compile_flags
    fs = get_flags(Compiler.GCC, CostModel.DEFAULT, math=True)
    assert "-fveclib=libmvec" not in fs.compile_flags
    fs = get_flags(Compiler.ICPX, CostModel.DEFAULT, math=True)
    assert "-fveclib=libmvec" not in fs.compile_flags


def test_link_flags_constant():
    """Link flags never change with cost-model; only compile-side does."""
    for fs in iter_combinations(cpu="intel_xeon"):
        assert fs.link_flags == LINK_BASE_FLAGS


def test_iter_combinations_count():
    """3 compilers x 4 cost-models = 12 sets per CPU."""
    sets = list(iter_combinations(cpu="intel_xeon"))
    assert len(sets) == 12
    assert {fs.compiler for fs in sets} == set(Compiler)
    assert {fs.cost_model for fs in sets} == set(CostModel)


def test_extra_flags_appended_last():
    fs = get_flags(Compiler.GCC,
                   CostModel.CHEAP,
                   cpu="intel_xeon",
                   extra=("-fvect-cost-model=cheap", "-fsimd-cost-model=cheap"))
    assert fs.compile_flags[-2:] == ("-fvect-cost-model=cheap", "-fsimd-cost-model=cheap")


# ---------------------------------------------------------------------------
#  ArmAutovecPreference: GCC --param aarch64-autovec-preference selector
# ---------------------------------------------------------------------------


def test_arm_autovec_sve_only_added_for_gcc_on_aarch64():
    """``ArmAutovecPreference.SVE_ONLY`` produces the documented GCC
    ``--param`` flag on an aarch64 SKU."""
    from vectra_artifacts.compilers import ArmAutovecPreference
    fs = get_flags(Compiler.GCC, CostModel.DEFAULT, cpu="arm_grace", arm_autovec=ArmAutovecPreference.SVE_ONLY)
    assert "--param=aarch64-autovec-preference=sve-only" in fs.compile_flags
    assert fs.arm_autovec is ArmAutovecPreference.SVE_ONLY


def test_arm_autovec_asimd_only_uses_correct_value():
    from vectra_artifacts.compilers import ArmAutovecPreference
    fs = get_flags(Compiler.GCC, CostModel.DEFAULT, cpu="fugaku_a64fx", arm_autovec=ArmAutovecPreference.ASIMD_ONLY)
    assert "--param=aarch64-autovec-preference=asimd-only" in fs.compile_flags


def test_arm_autovec_dropped_on_x86_cpu():
    """The knob is GCC-on-aarch64 only; an x86 SKU silently drops it
    so an unwary caller doesn't end up with an unrecognised flag."""
    from vectra_artifacts.compilers import ArmAutovecPreference
    fs = get_flags(Compiler.GCC, CostModel.DEFAULT, cpu="intel_xeon", arm_autovec=ArmAutovecPreference.SVE_ONLY)
    assert not any("aarch64-autovec-preference" in f for f in fs.compile_flags)
    # FlagSet still records the intent so source.sh / DB rows can audit it.
    assert fs.arm_autovec is ArmAutovecPreference.SVE_ONLY


def test_arm_autovec_dropped_for_clang():
    """Non-GCC compilers ignore the param; LLVM's ARM SVE-vs-NEON
    selection goes through target features, not a single flag."""
    from vectra_artifacts.compilers import ArmAutovecPreference
    fs = get_flags(Compiler.CLANG, CostModel.DEFAULT, cpu="arm_grace", arm_autovec=ArmAutovecPreference.SVE_ONLY)
    assert not any("aarch64-autovec-preference" in f for f in fs.compile_flags)


def test_arm_autovec_rationale_mentions_param():
    from vectra_artifacts.compilers import ArmAutovecPreference
    fs = get_flags(Compiler.GCC, CostModel.DEFAULT, cpu="arm_grace", arm_autovec=ArmAutovecPreference.SVE_ONLY)
    assert "aarch64-autovec-preference" in fs.rationale
