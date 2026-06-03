"""Populate + queries: round-trip the audit, the run grid, the summary."""
import pytest

from vectra_artifacts.compilers import Compiler, CostModel
from vectra_artifacts.database import (Suite, connect, create_schema, insert_kernel_audit_rows, insert_runs_bulk,
                                       summary_grid)
from vectra_artifacts.database.schema import add_cpu_models


@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / "v.db")
    create_schema(conn)
    add_cpu_models(conn, [("cpu1", "x86_64", 512, ""), ("cpu2", "aarch64", 128, "")])
    insert_kernel_audit_rows(conn, Suite.TSVC_2, [
        {
            "name": "k_one",
            "parallel_in_principle": "yes",
            "dace_status": "M"
        },
        {
            "name": "k_two",
            "parallel_in_principle": "no",
            "dace_status": "L (✗)"
        },
    ])
    yield conn
    conn.close()


def test_kernel_insert_round_trip(db):
    rows = db.execute("SELECT name, parallel_in_principle, dace_status FROM kernels").fetchall()
    by_name = {r["name"]: r for r in rows}
    assert by_name["k_one"]["parallel_in_principle"] == "yes"
    assert by_name["k_two"]["dace_status"] == "L (✗)"


def test_insert_kernel_audit_upserts(db):
    """Re-inserting the same name updates the row, not duplicates."""
    insert_kernel_audit_rows(db, Suite.TSVC_2, [{"name": "k_one", "notes": "rev2"}])
    rows = db.execute("SELECT name FROM kernels").fetchall()
    assert len({r["name"] for r in rows}) == 2  # still two kernels
    notes = db.execute("SELECT notes FROM kernels WHERE name='k_one'").fetchone()["notes"]
    assert notes == "rev2"


def test_runs_bulk_and_summary(db):
    # Every combination, both math values.
    runs = []
    for cpu in ("cpu1", "cpu2"):
        for c in Compiler:
            for cm in CostModel:
                for k, vec in (("k_one", True), ("k_two", False)):
                    runs.append({
                        "cpu": cpu,
                        "compiler": c.value,
                        "cost_model": cm.value,
                        "math": False,
                        "suite": Suite.TSVC_2,
                        "kernel": k,
                        "vectorized": vec,
                    })
    n = insert_runs_bulk(db, runs)
    assert n == 2 * 3 * 3 * 2  # cpus x compilers x cost-models x kernels
    grid = summary_grid(db, suites=[Suite.TSVC_2])
    # Each cell has 2 kernels, 1 vectorized.
    for cpu in ("cpu1", "cpu2"):
        for c in Compiler:
            for cm in CostModel:
                assert grid[(cpu, c.value, cm.value)] == (1, 2)


def test_summary_grid_math_filter(db):
    """Math filter narrows the aggregate."""
    insert_runs_bulk(
        db,
        [
            {
                "cpu": "cpu1",
                "compiler": Compiler.CLANG.value,
                "cost_model": CostModel.DEFAULT.value,
                "math": True,
                "suite": Suite.TSVC_2,
                "kernel": "k_one",
                "vectorized": True,
            },
            {
                "cpu": "cpu1",
                "compiler": Compiler.CLANG.value,
                "cost_model": CostModel.DEFAULT.value,
                "math": False,
                "suite": Suite.TSVC_2,
                "kernel": "k_one",
                "vectorized": False,
            },
        ],
    )
    g_math = summary_grid(db, math=True)
    g_nomath = summary_grid(db, math=False)
    assert g_math[("cpu1", Compiler.CLANG.value, CostModel.DEFAULT.value)] == (1, 1)
    assert g_nomath[("cpu1", Compiler.CLANG.value, CostModel.DEFAULT.value)] == (0, 1)


def test_summary_grid_suite_filter(db):
    """Restricting to a suite with no runs returns empty dict."""
    g = summary_grid(db, suites=[Suite.TSVC_2_5])
    assert g == {}
