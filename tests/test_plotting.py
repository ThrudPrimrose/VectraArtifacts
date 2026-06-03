"""Plotting tests: markdown grid + LaTeX grid + audit markdown render
predictable output from a seeded DB."""
import pytest

from vectra_artifacts.compilers import Compiler, CostModel
from vectra_artifacts.database import (Suite, connect, create_schema, insert_kernel_audit_rows, insert_runs_bulk)
from vectra_artifacts.database.schema import add_cpu_models
from vectra_artifacts.plotting import (render_grid_latex, render_grid_markdown, render_kernel_audit_markdown)


@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / "v.db")
    create_schema(conn)
    add_cpu_models(conn, [("cpu1", "x86_64", 512, ""), ("cpu2", "aarch64", 128, "")])
    insert_kernel_audit_rows(conn, Suite.TSVC_2, [
        {
            "name": "k1",
            "category": "linear",
            "parallel_in_principle": "yes",
            "dace_status": "M"
        },
        {
            "name": "k2",
            "category": "ind. var.",
            "parallel_in_principle": "no",
            "dace_status": "L"
        },
    ])
    runs = []
    for cpu in ("cpu1", "cpu2"):
        for c in Compiler:
            for cm in CostModel:
                for k in ("k1", "k2"):
                    runs.append({
                        "cpu": cpu,
                        "compiler": c.value,
                        "cost_model": cm.value,
                        "suite": Suite.TSVC_2,
                        "kernel": k,
                        "vectorized": (k == "k1" and cm != CostModel.NO),
                    })
    insert_runs_bulk(conn, runs)
    yield conn
    conn.close()


def test_grid_markdown_has_2_data_rows_and_9_cols(db):
    md = render_grid_markdown(db, suites=[Suite.TSVC_2])
    # Header + separator + 2 CPU rows = 4 lines (plus trailing newline).
    lines = [l for l in md.strip().split("\n") if l]
    assert len(lines) == 4
    # Header has 10 cells (1 CPU + 9 data cells).
    headers = [c.strip() for c in lines[0].split("|") if c.strip()]
    assert len(headers) == 10


def test_grid_markdown_cell_format(db):
    md = render_grid_markdown(db, suites=[Suite.TSVC_2])
    # k1 vectorizes for default+cheap, not no; k2 never vectorizes.
    # So default/cheap cells = 1/2, no cells = 0/2.
    assert "1/2" in md
    assert "0/2" in md


def test_grid_latex_structure(db):
    tex = render_grid_latex(db, suites=[Suite.TSVC_2])
    # Must wrap in table* (double-column), use booktabs rules, group by
    # compiler.
    assert r"\begin{table*}" in tex
    assert r"\end{table*}" in tex
    assert r"\toprule" in tex
    assert r"\bottomrule" in tex
    assert r"\multicolumn{3}{" in tex  # compiler header span
    # Cell content present.
    assert "1/2" in tex


def test_audit_markdown_has_one_row_per_kernel(db):
    md = render_kernel_audit_markdown(db, suites=[Suite.TSVC_2])
    lines = [l for l in md.strip().split("\n") if l]
    # header + sep + 2 kernel rows = 4.
    assert len(lines) == 4
    assert "k1" in md and "k2" in md


def test_audit_markdown_multi_suite_prepends_suite_col(db):
    insert_kernel_audit_rows(db, Suite.TSVC_2_5, [{"name": "ext_k1", "parallel_in_principle": "yes"}])
    md = render_kernel_audit_markdown(db)
    assert "Suite" in md
    assert Suite.TSVC_2.value in md
    assert Suite.TSVC_2_5.value in md
