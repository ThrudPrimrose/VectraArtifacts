"""Schema + seed tests: tables exist, seed populates static lookups,
re-running is idempotent."""
import sqlite3

import pytest

from vectra_artifacts.compilers import Compiler, CostModel
from vectra_artifacts.database import Suite, connect, create_schema
from vectra_artifacts.database.schema import SCHEMA_VERSION, add_cpu_models, get_schema_version


@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / "v.db")
    create_schema(conn)
    yield conn
    conn.close()


def test_tables_present(db):
    expected = {"_meta", "suites", "cpu_models", "compilers", "cost_models", "compiler_flags", "kernels", "runs"}
    cur = db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    have = {row["name"] for row in cur.fetchall()}
    assert expected <= have, f"missing tables: {expected - have}"


def test_schema_version_stamped(db):
    assert get_schema_version(db) == SCHEMA_VERSION


def test_suites_seeded(db):
    names = {row["name"] for row in db.execute("SELECT name FROM suites")}
    assert names == {s.value for s in Suite}


def test_compilers_seeded(db):
    rows = db.execute("SELECT name, executable FROM compilers").fetchall()
    by_name = {r["name"]: r["executable"] for r in rows}
    assert by_name[Compiler.CLANG.value] == "clang++"
    assert by_name[Compiler.GCC.value] == "g++"
    assert by_name[Compiler.ICPX.value] == "icpx"


def test_cost_models_seeded(db):
    names = {row["name"] for row in db.execute("SELECT name FROM cost_models")}
    assert names == {c.value for c in CostModel}


def test_compiler_flags_seeded(db):
    """3 compilers x 4 cost models x 2 math = 24 rows."""
    n = db.execute("SELECT COUNT(*) FROM compiler_flags").fetchone()[0]
    assert n == 24
    # Spot check: clang cheap math=1 has -fveclib=libmvec, gcc cheap math=1
    # does NOT (gcc handles libmvec implicitly).
    clang_cheap_math = db.execute(
        "SELECT flags FROM compiler_flags WHERE compiler=? AND cost_model=? AND math=?",
        (Compiler.CLANG.value, CostModel.CHEAP.value, 1),
    ).fetchone()["flags"]
    assert "-fveclib=libmvec" in clang_cheap_math
    gcc_cheap_math = db.execute(
        "SELECT flags FROM compiler_flags WHERE compiler=? AND cost_model=? AND math=?",
        (Compiler.GCC.value, CostModel.CHEAP.value, 1),
    ).fetchone()["flags"]
    assert "-fveclib=libmvec" not in gcc_cheap_math


def test_seed_is_idempotent(db):
    """Calling create_schema twice must not duplicate seed rows."""
    create_schema(db)
    create_schema(db)
    n = db.execute("SELECT COUNT(*) FROM compiler_flags").fetchone()[0]
    assert n == 24


def test_add_cpu_models(db):
    add_cpu_models(db, [
        ("cpu1", "x86_64", 512, "AVX-512 host"),
        ("cpu2", "aarch64", 128, "NEON host"),
    ])
    rows = {row["name"]: row["max_vec_width"] for row in db.execute("SELECT * FROM cpu_models")}
    assert rows == {"cpu1": 512, "cpu2": 128}
    add_cpu_models(db, [("cpu1", "x86_64", 256, "...")])  # idempotent
    assert db.execute("SELECT COUNT(*) FROM cpu_models").fetchone()[0] == 2


def test_runs_fk_violation_rejected(db):
    """Inserting a run pointing at a non-existent kernel must fail."""
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO runs(cpu, compiler, cost_model, math, suite, kernel, vectorized) "
            "VALUES(?, ?, ?, 0, ?, ?, 1)",
            ("cpu1", Compiler.CLANG.value, CostModel.DEFAULT.value, Suite.TSVC_2.value, "noexist"),
        )
        db.commit()
