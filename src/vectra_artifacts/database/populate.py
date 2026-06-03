"""Ingest helpers: kernel-audit rows and run results.

The schema's static lookups (suites, compilers, cost_models,
compiler_flags) are seeded by :func:`create_schema`. This module covers
the two dynamic surfaces:

* per-kernel audit rows (parsed from ``docs/PARALLELIZATION_AUDIT.md``
  or its tsvc_2_5 analogue),
* run records (one row per (cpu, compiler, cost-model, math, kernel)
  measurement).
"""
from __future__ import annotations

import sqlite3
from typing import Iterable, Mapping, Optional, Sequence

from .schema import Suite

# Audit-row fields, in the order they're stored in the ``kernels`` table.
_KERNEL_COLS = (
    "suite",
    "name",
    "category",
    "tsvc_comment",
    "loop_shape",
    "parallel_in_principle",
    "blocking_factor",
    "dace_status",
    "notes",
)


def insert_kernel_audit_rows(conn: sqlite3.Connection, suite: Suite, rows: Iterable[Mapping[str, str]]) -> int:
    """Insert / upsert kernel-audit rows for one suite.

    Each row is a mapping with the keys
    ``name, category, tsvc_comment, loop_shape, parallel_in_principle,
    blocking_factor, dace_status, notes`` -- a subset is fine; missing
    keys default to empty string.

    Returns the number of rows written.
    """
    payload: list = []
    for r in rows:
        payload.append((
            suite.value,
            r["name"],
            r.get("category", ""),
            r.get("tsvc_comment", ""),
            r.get("loop_shape", ""),
            r.get("parallel_in_principle", ""),
            r.get("blocking_factor", ""),
            r.get("dace_status", ""),
            r.get("notes", ""),
        ))
    cols = ", ".join(_KERNEL_COLS)
    qmarks = ", ".join("?" * len(_KERNEL_COLS))
    update_cols = ", ".join(f"{c} = excluded.{c}" for c in _KERNEL_COLS if c not in ("suite", "name"))
    conn.executemany(
        f"INSERT INTO kernels({cols}) VALUES({qmarks}) "
        f"ON CONFLICT(suite, name) DO UPDATE SET {update_cols}",
        payload,
    )
    conn.commit()
    return len(payload)


def insert_run(conn: sqlite3.Connection,
               *,
               cpu: str,
               compiler: str,
               cost_model: str,
               math: bool,
               suite: Suite,
               kernel: str,
               vectorized: bool,
               exec_us: Optional[float] = None) -> int:
    """Insert a single run record. Returns the new row's autoincrement id."""
    cur = conn.execute(
        "INSERT INTO runs(cpu, compiler, cost_model, math, suite, kernel, vectorized, exec_us) "
        "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
        (cpu, compiler, cost_model, 1 if math else 0, suite.value, kernel, 1 if vectorized else 0, exec_us),
    )
    conn.commit()
    return cur.lastrowid


def insert_runs_bulk(conn: sqlite3.Connection, rows: Sequence[Mapping]) -> int:
    """Bulk insert run records. ``rows`` is a sequence of mappings with
    the keys accepted by :func:`insert_run`. Returns the count written.
    """
    payload = []
    for r in rows:
        suite = r["suite"]
        if isinstance(suite, Suite):
            suite = suite.value
        payload.append((
            r["cpu"],
            r["compiler"],
            r["cost_model"],
            1 if r.get("math", False) else 0,
            suite,
            r["kernel"],
            1 if r["vectorized"] else 0,
            r.get("exec_us"),
        ))
    conn.executemany(
        "INSERT INTO runs(cpu, compiler, cost_model, math, suite, kernel, vectorized, exec_us) "
        "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
        payload,
    )
    conn.commit()
    return len(payload)


def list_suites(conn: sqlite3.Connection) -> list:
    return [row["name"] for row in conn.execute("SELECT name FROM suites ORDER BY name")]
