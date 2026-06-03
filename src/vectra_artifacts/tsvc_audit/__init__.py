"""TSVC parallelization-audit ingestion.

Parses ``docs/PARALLELIZATION_AUDIT.md`` (and the analogous file for the
``tsvc_2_5`` suite) into structured rows the database layer
can ingest. Format is the pipe-delimited Markdown table the research
agent wrote; columns are matched by header name, not position.
"""
from .tsvc_2_5_seed import seed_tsvc_2_5
from .parser import parse_audit_markdown, AUDIT_COLUMNS

__all__ = ["parse_audit_markdown", "AUDIT_COLUMNS", "seed_tsvc_2_5"]
