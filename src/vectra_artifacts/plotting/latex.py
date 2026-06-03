"""LaTeX rendering: perf grid as a double-column ``table*`` block.

The grid spans 9 data columns (3 compilers x 3 cost-models) which is
too wide for a single column in a typical two-column paper layout, so
the table is wrapped in ``\\begin{table*}`` so it spans both columns by
default. ``\\multicolumn`` groups each compiler's three cost-model
columns under one merged header.
"""
from __future__ import annotations

import sqlite3
from typing import Iterable, List, Optional

from ..compilers.flags import Compiler, CostModel
from ..database.queries import COMPILER_ORDER, COST_MODEL_ORDER, list_cpus, summary_grid
from ..database.schema import Suite


def _escape_latex_cell(s: str) -> str:
    """Minimal LaTeX escape for the cells we write: backslash, underscore,
    percent, hash, ampersand, dollar, caret, tilde, braces."""
    for char, repl in (
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ):
        s = s.replace(char, repl)
    return s


def _cell(cpu: str, compiler: Compiler, cm: CostModel, grid: dict, empty: str = "--") -> str:
    val = grid.get((cpu, compiler.value, cm.value))
    if val is None:
        return empty
    vec, total = val
    return f"{vec}/{total}"


def render_grid_latex(conn: sqlite3.Connection,
                      *,
                      suites: Optional[Iterable[Suite]] = None,
                      math: Optional[bool] = None,
                      caption: str = "Vectorized kernels per (CPU, compiler, cost-model). "
                      "Cells show ``vectorized / total``.",
                      label: str = "tab:vectorization-grid",
                      empty: str = "--") -> str:
    """Render the perf grid as a double-column ``table*`` block.

    Output is ready to ``\\input{...}`` into a two-column paper. Uses
    ``booktabs`` macros (``\\toprule``, ``\\midrule``, ``\\bottomrule``);
    ensure the document loads the ``booktabs`` package.
    """
    grid = summary_grid(conn, suites=suites, math=math)
    cpus = list_cpus(conn)
    if not cpus:
        return "% (no CPU models registered)\n"

    # Column spec: ``l`` for the CPU label, then 3 groups of 3 ``c``
    # columns separated by ``|`` rules.
    col_groups = "|".join(["ccc"] * len(COMPILER_ORDER))
    col_spec = "l|" + col_groups
    n_data = 3 * len(COMPILER_ORDER)

    lines: List[str] = []
    lines.append(r"\begin{table*}")
    lines.append(r"  \centering")
    # Caption is treated as user-supplied LaTeX: passed verbatim so
    # callers can include math, citations, ``\texttt{...}`` etc. Body
    # cells are still escaped.
    lines.append(rf"  \caption{{{caption}}}")
    lines.append(rf"  \label{{{label}}}")
    lines.append(rf"  \begin{{tabular}}{{{col_spec}}}")
    lines.append(r"    \toprule")

    # Compiler row: each compiler name spans 3 cost-model columns.
    compiler_cells = [r"\textbf{CPU}"]
    for compiler in COMPILER_ORDER:
        compiler_cells.append(rf"\multicolumn{{3}}{{c}}{{\textbf{{{_escape_latex_cell(compiler.value)}}}}}")
    lines.append("    " + " & ".join(compiler_cells) + r" \\")

    # Sub-row: cost-model names under each compiler.
    sub_cells = [""]
    for _compiler in COMPILER_ORDER:
        for cm in COST_MODEL_ORDER:
            sub_cells.append(_escape_latex_cell(cm.value))
    lines.append("    " + " & ".join(sub_cells) + r" \\")
    lines.append(r"    \midrule")

    for cpu in cpus:
        row_cells = [_escape_latex_cell(cpu)]
        for compiler in COMPILER_ORDER:
            for cm in COST_MODEL_ORDER:
                row_cells.append(_cell(cpu, compiler, cm, grid, empty=empty))
        lines.append("    " + " & ".join(row_cells) + r" \\")
    lines.append(r"    \bottomrule")
    lines.append(r"  \end{tabular}")
    lines.append(r"\end{table*}")
    return "\n".join(lines) + "\n"
