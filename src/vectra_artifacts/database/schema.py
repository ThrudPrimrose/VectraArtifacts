"""SQLite schema for the vectorization perf-grid database.

Six tables (plus one for schema metadata):

* ``suites``        -- ``tsvc_2`` and ``tsvc_2_5``.
* ``cpu_models``    -- one row per CPU SKU exercised in the sweep.
* ``compilers``     -- ``clang`` / ``gcc`` / ``icpx``.
* ``cost_models``   -- ``default`` / ``cheap`` / ``unlimited`` / ``disabled``.
* ``compiler_flags`` -- the (compiler, cost-model, math) flag list,
                       seeded from :mod:`vectra_artifacts.compilers.flags`.
* ``kernels``       -- per-(suite, name) audit row.
* ``runs``          -- per-(cpu, compiler, cost-model, kernel) outcome.

Static lookup tables are seeded at schema-creation time (per-CPU rows are
caller-managed). Re-creating the schema is idempotent: each
``CREATE TABLE`` is ``IF NOT EXISTS`` and seeds use ``ON CONFLICT DO
NOTHING``.
"""
from __future__ import annotations

import enum
import pathlib
import sqlite3
from typing import Iterable, Optional, Sequence

#: Schema version stamped into ``_meta`` at create time. Bump when
#: changing any DDL so downstream tooling can detect mismatches.
SCHEMA_VERSION = 1

#: Default on-disk location relative to the package install. Callers
#: usually override with a project-specific path; this is just the
#: "where do I look if nothing is configured" answer.
DEFAULT_DB_PATH = pathlib.Path("./vectra.db")


class Suite(enum.Enum):
    """Kernel-suite identifier. Stored as the string value in the DB."""
    TSVC_2 = "tsvc_2"
    TSVC_2_5 = "tsvc_2_5"


SCHEMA_DDL: str = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS _meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS suites (
    name        TEXT PRIMARY KEY,
    description TEXT
);

CREATE TABLE IF NOT EXISTS cpu_models (
    name           TEXT PRIMARY KEY,
    arch           TEXT,
    max_vec_width  INTEGER,
    description    TEXT
);

CREATE TABLE IF NOT EXISTS compilers (
    name        TEXT PRIMARY KEY,
    executable  TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS cost_models (
    name        TEXT PRIMARY KEY,
    description TEXT
);

CREATE TABLE IF NOT EXISTS compiler_flags (
    compiler     TEXT NOT NULL REFERENCES compilers(name),
    cost_model   TEXT NOT NULL REFERENCES cost_models(name),
    math         INTEGER NOT NULL CHECK (math IN (0,1)),
    flags        TEXT NOT NULL,
    rationale    TEXT,
    PRIMARY KEY (compiler, cost_model, math)
);

CREATE TABLE IF NOT EXISTS kernels (
    suite                  TEXT NOT NULL REFERENCES suites(name),
    name                   TEXT NOT NULL,
    category               TEXT,
    tsvc_comment           TEXT,
    loop_shape             TEXT,
    parallel_in_principle  TEXT,
    blocking_factor        TEXT,
    dace_status            TEXT,
    notes                  TEXT,
    PRIMARY KEY (suite, name)
);

CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    cpu           TEXT NOT NULL REFERENCES cpu_models(name),
    compiler      TEXT NOT NULL REFERENCES compilers(name),
    cost_model    TEXT NOT NULL REFERENCES cost_models(name),
    math          INTEGER NOT NULL DEFAULT 0 CHECK (math IN (0,1)),
    suite         TEXT NOT NULL REFERENCES suites(name),
    kernel        TEXT NOT NULL,
    vectorized    INTEGER NOT NULL CHECK (vectorized IN (0,1)),
    exec_us       REAL,
    ts            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (suite, kernel) REFERENCES kernels(suite, name)
);

CREATE INDEX IF NOT EXISTS runs_lookup_idx
    ON runs (cpu, compiler, cost_model, suite);
"""


def connect(db_path: Optional[pathlib.Path] = None) -> sqlite3.Connection:
    """Open the SQLite database, enabling foreign keys.

    Creates parent dirs and the file if it doesn't exist. Returns a
    connection with ``row_factory = sqlite3.Row`` so callers can read
    rows as mappings.
    """
    path = pathlib.Path(db_path or DEFAULT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def create_schema(conn: sqlite3.Connection, *, seed: bool = True) -> None:
    """Create every table and seed the static lookup tables (suites,
    compilers, cost models, compiler_flags) from the canonical Python
    data. Idempotent."""
    conn.executescript(SCHEMA_DDL)
    conn.execute("INSERT OR REPLACE INTO _meta(key,value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION), ))
    if seed:
        seed_static_tables(conn)
    conn.commit()


def get_schema_version(conn: sqlite3.Connection) -> Optional[int]:
    row = conn.execute("SELECT value FROM _meta WHERE key='schema_version'").fetchone()
    return int(row["value"]) if row else None


def seed_static_tables(conn: sqlite3.Connection) -> None:
    """Idempotently seed suites + compilers + cost_models + compiler_flags
    from the canonical Python data in
    :mod:`vectra_artifacts.compilers.flags`."""
    # Local import: avoids a circular import at module load time and
    # keeps :mod:`schema` usable without :mod:`compilers` installed.
    from ..compilers.flags import Compiler, CostModel, EXECUTABLE_BY_COMPILER, get_flags

    conn.executemany(
        "INSERT INTO suites(name, description) VALUES(?, ?) ON CONFLICT(name) DO NOTHING",
        [
            (Suite.TSVC_2.value, "Standard TSVC-2 corpus (Levine/Callahan/Maslov; 151 kernels)."),
            (Suite.TSVC_2_5.value, "VectraArtifacts extension corpus -- symbolic step sizes, "
             "symbolic offsets, quasi-affine ``//2`` patterns and other "
             "kernels where Pluto-class polyhedral tools fail."),
        ],
    )
    conn.executemany(
        "INSERT INTO compilers(name, executable, description) VALUES(?, ?, ?) ON CONFLICT(name) DO NOTHING",
        [
            (Compiler.CLANG.value, EXECUTABLE_BY_COMPILER[Compiler.CLANG], "LLVM clang / clang++."),
            (Compiler.GCC.value, EXECUTABLE_BY_COMPILER[Compiler.GCC], "GNU g++."),
            (Compiler.ICPX.value, EXECUTABLE_BY_COMPILER[Compiler.ICPX], "Intel oneAPI icpx (LLVM-based)."),
        ],
    )
    conn.executemany(
        "INSERT INTO cost_models(name, description) VALUES(?, ?) ON CONFLICT(name) DO NOTHING",
        [
            (CostModel.DEFAULT.value, "Baseline -O3 vector flags; no extra cost-model hint."),
            (CostModel.CHEAP.value, "Lighter cost-model variant (width hint on clang/gcc, "
             "-qopt-zmm-usage on icpx)."),
            (CostModel.UNLIMITED.value, "Vectorization unlimited, no reduction (-fvectorize / -vec)."),
            (CostModel.DISABLED.value, "Vectorization disabled (-fno-vectorize / -no-vec)."),
        ],
    )
    rows: list = []
    for compiler in Compiler:
        for cm in CostModel:
            for math in (False, True):
                fs = get_flags(compiler, cm, math=math)
                rows.append((compiler.value, cm.value, 1 if math else 0, fs.compile_flag_str(), fs.rationale))
    conn.executemany(
        "INSERT INTO compiler_flags(compiler, cost_model, math, flags, rationale) "
        "VALUES(?, ?, ?, ?, ?) ON CONFLICT(compiler, cost_model, math) DO UPDATE SET "
        "flags = excluded.flags, rationale = excluded.rationale",
        rows,
    )
    conn.commit()


def add_cpu_models(conn: sqlite3.Connection, rows: Sequence[Sequence]) -> None:
    """Bulk insert ``(name, arch, max_vec_width, description)`` rows
    into ``cpu_models`` (idempotent)."""
    conn.executemany(
        "INSERT INTO cpu_models(name, arch, max_vec_width, description) "
        "VALUES(?, ?, ?, ?) ON CONFLICT(name) DO NOTHING",
        list(rows),
    )
    conn.commit()


def list_table(conn: sqlite3.Connection, table: str) -> Iterable[sqlite3.Row]:
    """Convenience iterator over a whole table -- diagnostic only."""
    yield from conn.execute(f"SELECT * FROM {table}").fetchall()
