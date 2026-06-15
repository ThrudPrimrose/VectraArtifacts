"""Aggregate queries powering the markdown / LaTeX plotters.

Two high-level read APIs:

* :func:`kernel_audit_rows` -- iterate the per-kernel rows (one suite, all,
  filtered by predicate). Backs the audit-markdown rendering.
* :func:`summary_grid` -- the 9-column grid: CPU x (compiler, cost_model) ->
  ``(vectorized_count, total)``. Backs the perf-grid markdown / LaTeX.

Both honour the suite filter (one suite, both -- but always at least one
kernel in the requested suite or the answer is empty).
"""
from __future__ import annotations

import sqlite3
from typing import Dict, Iterable, List, Optional, Tuple

from ..compilers.flags import Compiler, CostModel
from .schema import Suite


def _suite_filter_clause(suites: Optional[Iterable[Suite]]) -> Tuple[str, list]:
    """Build a ``(clause, params)`` pair for restricting to a suite set.
    Returns ``('', [])`` when the caller wants every suite."""
    if not suites:
        return "", []
    names = [s.value if isinstance(s, Suite) else s for s in suites]
    placeholders = ", ".join("?" * len(names))
    return f"AND k.suite IN ({placeholders})", names


def kernel_audit_rows(conn: sqlite3.Connection, suites: Optional[Iterable[Suite]] = None) -> List[sqlite3.Row]:
    """Return audit rows ordered by ``(suite, name)`` for one or more
    suites. ``suites=None`` means "every suite"."""
    if suites is None:
        return conn.execute("SELECT * FROM kernels ORDER BY suite, name").fetchall()
    names = [s.value if isinstance(s, Suite) else s for s in suites]
    placeholders = ", ".join("?" * len(names))
    return conn.execute(
        f"SELECT * FROM kernels WHERE suite IN ({placeholders}) ORDER BY suite, name",
        names,
    ).fetchall()


def summary_grid(conn: sqlite3.Connection,
                 *,
                 suites: Optional[Iterable[Suite]] = None,
                 math: Optional[bool] = None) -> Dict[Tuple[str, str, str], Tuple[int, int]]:
    """Return the (cpu, compiler, cost_model) -> (vectorized, total) grid.

    :param suites: restrict to these kernel suites (default: all suites).
    :param math: if ``True`` / ``False``, restrict to that math-flag.
                 ``None`` (default) aggregates across both.
    :returns: a dict keyed by ``(cpu, compiler, cost_model)`` where the
              value is ``(vectorized_count, total_runs)``. CPUs/compilers/
              cost-models with no rows are absent from the dict.
    """
    suite_clause, suite_params = _suite_filter_clause(suites)
    math_clause = ""
    math_params: List = []
    if math is not None:
        math_clause = "AND r.math = ?"
        math_params = [1 if math else 0]
    sql = f"""
        SELECT
            r.cpu        AS cpu,
            r.compiler   AS compiler,
            r.cost_model AS cost_model,
            SUM(r.vectorized) AS vectorized,
            COUNT(*)          AS total
        FROM runs r
        JOIN kernels k ON r.suite = k.suite AND r.kernel = k.name
        WHERE 1=1 {suite_clause} {math_clause}
        GROUP BY r.cpu, r.compiler, r.cost_model
    """
    out: Dict[Tuple[str, str, str], Tuple[int, int]] = {}
    for row in conn.execute(sql, suite_params + math_params).fetchall():
        out[(row["cpu"], row["compiler"], row["cost_model"])] = (
            int(row["vectorized"]),
            int(row["total"]),
        )
    return out


def list_cpus(conn: sqlite3.Connection) -> List[str]:
    """All registered CPU names, sorted; populated either via
    ``add_cpu_models`` or implicitly by inserted runs (a run with an
    unknown cpu still surfaces here so the grid stays complete)."""
    cur = conn.execute("SELECT name FROM cpu_models ORDER BY name")
    declared = [r["name"] for r in cur.fetchall()]
    cur = conn.execute("SELECT DISTINCT cpu FROM runs ORDER BY cpu")
    seen = [r["cpu"] for r in cur.fetchall() if r["cpu"] not in declared]
    return declared + seen


COMPILER_ORDER: Tuple[Compiler, ...] = (Compiler.CLANG, Compiler.GCC, Compiler.ICPX)
COST_MODEL_ORDER: Tuple[CostModel, ...] = (CostModel.DEFAULT, CostModel.CHEAP, CostModel.UNLIMITED, CostModel.DISABLED)
