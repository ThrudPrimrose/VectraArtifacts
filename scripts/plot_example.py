#!/usr/bin/env python3
"""Render the perf grid + audit table from ``./vectra.db``.

Sister script to ``populate_example.py``; run that first.
"""
import pathlib

from vectra_artifacts.database import connect
from vectra_artifacts.database.schema import Suite
from vectra_artifacts.plotting import (render_grid_latex, render_grid_markdown, render_kernel_audit_markdown)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "vectra.db"


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"no database at {DB_PATH}; run scripts/populate_example.py first.")
    conn = connect(DB_PATH)
    out_dir = REPO_ROOT / "build"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "grid.md").write_text(
        render_grid_markdown(conn, suites=[Suite.TSVC_2], caption="Demo perf grid (tsvc_2 only, math aggregated)."))
    (out_dir / "grid.tex").write_text(
        render_grid_latex(conn,
                          suites=[Suite.TSVC_2],
                          caption="Demo perf grid (tsvc\\_2 only). "
                          "Cells show \\texttt{vectorized / total} per (CPU, compiler, cost-model).",
                          label="tab:vectra-demo-grid"))
    (out_dir / "audit.md").write_text(
        render_kernel_audit_markdown(conn,
                                     suites=[Suite.TSVC_2],
                                     caption="TSVC-2 per-kernel audit (demo render from the database)."))
    print(f"wrote {out_dir/'grid.md'}")
    print(f"wrote {out_dir/'grid.tex'}")
    print(f"wrote {out_dir/'audit.md'}")


if __name__ == "__main__":
    main()
