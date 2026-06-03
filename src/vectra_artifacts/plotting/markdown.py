"""Markdown rendering: perf grid + per-kernel audit table."""
from __future__ import annotations

import sqlite3
from typing import Iterable, List, Optional, Sequence

from ..compilers.flags import Compiler, CostModel
from ..database.queries import COMPILER_ORDER, COST_MODEL_ORDER, list_cpus, summary_grid
from ..database.schema import Suite
from ..tsvc_audit.parser import AUDIT_COLUMNS


def _cell(cpu: str, compiler: Compiler, cm: CostModel, grid: dict, empty: str = "-") -> str:
    val = grid.get((cpu, compiler.value, cm.value))
    if val is None:
        return empty
    vec, total = val
    return f"{vec}/{total}"


def render_grid_markdown(conn: sqlite3.Connection,
                         *,
                         suites: Optional[Iterable[Suite]] = None,
                         math: Optional[bool] = None,
                         caption: Optional[str] = None,
                         empty: str = "-") -> str:
    """Render the CPU x (compiler, cost-model) perf grid as Markdown.

    Layout: rows = CPU models, columns = 3 compilers each with 3
    cost-model sub-columns = 9 data columns + 1 row-label column.
    Markdown's pipe tables can't merge column headers, so the first
    header row repeats the compiler name above each of its three
    cost-model cells (i.e. ``clang/default | clang/cheap | clang/no | ...``).

    Cell contents: ``vectorized/total``. Missing combinations show as
    ``empty`` (default ``-``).
    """
    grid = summary_grid(conn, suites=suites, math=math)
    cpus = list_cpus(conn)
    if not cpus:
        return "(no CPU models registered)"

    head_cells = ["CPU"]
    for compiler in COMPILER_ORDER:
        for cm in COST_MODEL_ORDER:
            head_cells.append(f"{compiler.value} / {cm.value}")
    sep_cells = ["---"] * len(head_cells)

    lines: List[str] = []
    if caption:
        lines.append(f"**{caption}**")
        lines.append("")
    lines.append("| " + " | ".join(head_cells) + " |")
    lines.append("| " + " | ".join(sep_cells) + " |")
    for cpu in cpus:
        row = [cpu]
        for compiler in COMPILER_ORDER:
            for cm in COST_MODEL_ORDER:
                row.append(_cell(cpu, compiler, cm, grid, empty=empty))
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


_AUDIT_HEADERS: Sequence[str] = (
    "Kernel",
    "Category",
    "TSVC comment",
    "Loop shape",
    "Parallel in principle?",
    "Blocking factor",
    "DaCe status",
    "Notes",
)


def _escape_md_cell(s: str) -> str:
    """Make a cell safe for a one-row markdown table cell: replace
    pipes (would split the cell) and newlines."""
    return s.replace("|", "\\|").replace("\n", " ").strip()


def render_kernel_audit_markdown(conn: sqlite3.Connection,
                                 *,
                                 suites: Optional[Iterable[Suite]] = None,
                                 include_columns: Optional[Sequence[str]] = None,
                                 caption: Optional[str] = None) -> str:
    """Render the per-kernel audit (1 row per kernel) as Markdown.

    :param suites: subset of suites to include (default: all suites,
                   in lexical name order; with multiple suites a
                   ``Suite`` column is prepended).
    :param include_columns: optional subset of the eight
                            :data:`~vectra_artifacts.tsvc_audit.parser.AUDIT_COLUMNS`
                            (default: every column).
    :param caption: optional bold caption line above the table.
    """
    from ..database.queries import kernel_audit_rows  # local import: avoid cycle
    rows = kernel_audit_rows(conn, suites=suites)
    if not rows:
        return "(no kernel rows; ingest the audit markdown first via ``vectra-populate``)"

    cols = list(include_columns) if include_columns else list(AUDIT_COLUMNS)
    multi_suite = (suites is None and len({r["suite"] for r in rows}) > 1) or (suites and len(list(suites)) > 1)

    head = (["Suite"] if multi_suite else []) + [_header_label(c) for c in cols]
    sep = ["---"] * len(head)
    lines: List[str] = []
    if caption:
        lines.append(f"**{caption}**")
        lines.append("")
    lines.append("| " + " | ".join(head) + " |")
    lines.append("| " + " | ".join(sep) + " |")
    for r in rows:
        row_cells: List[str] = []
        if multi_suite:
            row_cells.append(_escape_md_cell(r["suite"]))
        for c in cols:
            row_cells.append(_escape_md_cell(r[c] or ""))
        lines.append("| " + " | ".join(row_cells) + " |")
    return "\n".join(lines) + "\n"


def _header_label(col: str) -> str:
    return {
        "name": "Kernel",
        "category": "Category",
        "tsvc_comment": "TSVC comment",
        "loop_shape": "Loop shape",
        "parallel_in_principle": "Parallel in principle?",
        "blocking_factor": "Blocking factor",
        "dace_status": "DaCe status",
        "notes": "Notes",
    }.get(col,
          col.replace("_", " ").title())
