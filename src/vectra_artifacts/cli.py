"""CLI entry points wired in ``pyproject.toml``:

* ``vectra-populate``  -- ingest a parallelization-audit markdown file.
* ``vectra-plot``      -- render the perf grid or per-kernel audit table
                           as Markdown or LaTeX.
* ``vectra-source-sh`` -- emit a ``source.sh`` snippet for a chosen
                           (compiler, cost-model, math, cpu) combo.
"""
import argparse
import pathlib
import sys

from .compilers import Compiler, CostModel, source_sh, write_source_sh
from .database import (Suite, connect, create_schema, insert_kernel_audit_rows)
from .plotting import render_grid_latex, render_grid_markdown, render_kernel_audit_markdown
from .tsvc_audit import parse_audit_markdown


def _suite_from_str(s: str) -> Suite:
    for suite in Suite:
        if suite.value == s:
            return suite
    raise ValueError(f"unknown suite {s!r}; choose from {[s.value for s in Suite]}")


def main_populate(argv: list = None) -> int:
    """``vectra-populate`` -- read a PARALLELIZATION_AUDIT markdown file
    and write its rows into ``--db``. Creates the schema if missing."""
    p = argparse.ArgumentParser(prog="vectra-populate",
                                description="Ingest a parallelization-audit markdown into the SQLite DB.")
    p.add_argument("--audit", required=True, type=pathlib.Path, help="Path to a PARALLELIZATION_AUDIT.md file.")
    p.add_argument("--db", required=True, type=pathlib.Path, help="SQLite database file (created if missing).")
    p.add_argument("--suite",
                   default=Suite.TSVC_2.value,
                   choices=[s.value for s in Suite],
                   help="Which kernel suite these rows belong to.")
    args = p.parse_args(argv)

    suite = _suite_from_str(args.suite)
    rows = parse_audit_markdown(args.audit)
    conn = connect(args.db)
    create_schema(conn)
    n = insert_kernel_audit_rows(conn, suite, rows)
    print(f"populated {n} rows into {args.db} (suite={suite.value})")
    return 0


def main_plot(argv: list = None) -> int:
    """``vectra-plot`` -- render the perf grid or per-kernel audit as
    Markdown / LaTeX."""
    p = argparse.ArgumentParser(prog="vectra-plot", description="Render the perf grid or per-kernel audit table.")
    p.add_argument("--db", required=True, type=pathlib.Path)
    p.add_argument("--kind", choices=["grid-md", "grid-tex", "audit-md"], default="grid-md")
    p.add_argument("--suite",
                   action="append",
                   default=None,
                   choices=[s.value for s in Suite],
                   help="Restrict to one or more suites (repeatable).")
    p.add_argument("--math",
                   choices=["any", "0", "1"],
                   default="any",
                   help="Restrict the grid to math=0/1 rows or aggregate both (default 'any').")
    p.add_argument("--out", type=pathlib.Path, help="Optional output file (default: stdout).")
    p.add_argument("--caption", default=None)
    p.add_argument("--label", default="tab:vectorization-grid")
    args = p.parse_args(argv)

    conn = connect(args.db)
    suites = [_suite_from_str(s) for s in args.suite] if args.suite else None
    math = None if args.math == "any" else bool(int(args.math))

    if args.kind == "grid-md":
        text = render_grid_markdown(conn, suites=suites, math=math, caption=args.caption)
    elif args.kind == "grid-tex":
        text = render_grid_latex(conn,
                                 suites=suites,
                                 math=math,
                                 caption=args.caption or "Vectorized kernels per (CPU, compiler, cost-model). "
                                 "Cells show ``vectorized / total``.",
                                 label=args.label)
    else:
        text = render_kernel_audit_markdown(conn, suites=suites, caption=args.caption)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(text)
    return 0


def main_source_sh(argv: list = None) -> int:
    """``vectra-source-sh`` -- emit a sourceable shell snippet that sets
    CXX / EXTRA_FLAGS / LINK_FLAGS for one combination."""
    p = argparse.ArgumentParser(prog="vectra-source-sh", description="Emit a source.sh snippet for one combination.")
    p.add_argument("--compiler", required=True, choices=[c.value for c in Compiler])
    p.add_argument("--cost-model", required=True, choices=[c.value for c in CostModel])
    p.add_argument("--math", action="store_true", help="Include math-call vectorization flags.")
    p.add_argument("--cpu", default=None, help="Target CPU SKU (e.g. intel_xeon, amd_epyc).")
    p.add_argument("--out", type=pathlib.Path, help="Write to this file (default: stdout).")
    args = p.parse_args(argv)

    compiler = next(c for c in Compiler if c.value == args.compiler)
    cm = next(c for c in CostModel if c.value == args.cost_model)
    if args.out:
        write_source_sh(args.out, compiler=compiler, cost_model=cm, math=args.math, cpu=args.cpu)
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(source_sh(compiler=compiler, cost_model=cm, math=args.math, cpu=args.cpu))
    return 0
