"""source.sh generator: shape, env vars, executability."""
import pathlib
import stat

import pytest

from vectra_artifacts.compilers import Compiler, CostModel, source_sh, write_source_sh


@pytest.mark.parametrize("compiler", list(Compiler))
@pytest.mark.parametrize("cost_model", list(CostModel))
def test_source_sh_sets_required_env_vars(compiler, cost_model):
    text = source_sh(compiler=compiler, cost_model=cost_model, cpu="intel_xeon")
    for required in ("CXX=", "CXX_COMPILER=", "CXX_COSTMODEL=", "EXTRA_FLAGS=", "LINK_FLAGS="):
        assert required in text, f"missing {required} for {compiler.value}/{cost_model.value}"
    # Compiler executable + cost-model name verbatim in the output.
    assert compiler.executable() in text
    assert cost_model.value in text


def test_source_sh_math_flag_sets_cxx_math(tmp_path):
    text_no_math = source_sh(compiler=Compiler.CLANG, cost_model=CostModel.DEFAULT, math=False)
    text_math = source_sh(compiler=Compiler.CLANG, cost_model=CostModel.DEFAULT, math=True)
    assert "CXX_MATH='0'" in text_no_math
    assert "CXX_MATH='1'" in text_math
    assert "-fveclib=libmvec" in text_math


def test_write_source_sh_marks_executable(tmp_path):
    p = write_source_sh(tmp_path / "scripts" / "source.sh",
                        compiler=Compiler.GCC,
                        cost_model=CostModel.CHEAP,
                        cpu="amd_epyc")
    assert p.exists()
    mode = p.stat().st_mode
    assert mode & stat.S_IXUSR
    assert "-mprefer-vector-width=256" in p.read_text()
