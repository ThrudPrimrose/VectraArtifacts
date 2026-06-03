"""Two backends: Markdown and LaTeX. Three renderings:

* :func:`render_grid_markdown` -- the 9-column CPU x (compiler, cost-model)
  perf grid as a Markdown table; cell shows ``vectorized/total``.
* :func:`render_grid_latex` -- same grid as a double-column ``table*`` LaTeX
  block ready to paste into a paper.
* :func:`render_kernel_audit_markdown` -- the per-kernel audit table
  (one row per kernel, all eight columns).
"""
from .markdown import render_grid_markdown, render_kernel_audit_markdown
from .latex import render_grid_latex

__all__ = [
    "render_grid_markdown",
    "render_grid_latex",
    "render_kernel_audit_markdown",
]
