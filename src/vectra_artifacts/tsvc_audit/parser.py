"""Parse the per-kernel parallelization audit Markdown.

Recognises the pipe-delimited table the research agent emits at
``docs/PARALLELIZATION_AUDIT.md``. Robust against extra header / footer
text -- the parser scans for the first row whose header includes
``Kernel`` and ``DaCe status`` (case-insensitive), then consumes the
contiguous block of pipe rows below it.
"""
from __future__ import annotations

import pathlib
import re
from typing import Iterable, List, Mapping

#: Header text -> kernel-row dict key. Header matching is
#: case-insensitive and tolerates trailing question marks / parentheses.
_HEADER_TO_KEY: Mapping[str, str] = {
    "kernel": "name",
    "tsvc-2 category": "category",
    "original tsvc comment": "tsvc_comment",
    "loop shape": "loop_shape",
    "parallel in principle": "parallel_in_principle",
    "blocking factor": "blocking_factor",
    "dace canonicalize status": "dace_status",
    "dace status": "dace_status",
    "notes": "notes",
}

#: The audit row keys, in the canonical order. Useful for tests / round-trips.
AUDIT_COLUMNS = (
    "name",
    "category",
    "tsvc_comment",
    "loop_shape",
    "parallel_in_principle",
    "blocking_factor",
    "dace_status",
    "notes",
)

_HEADER_NORMALISE_RE = re.compile(r"[?()]")


def _normalise_header(cell: str) -> str:
    s = cell.strip().lower()
    s = _HEADER_NORMALISE_RE.sub("", s)
    return s.strip()


def _split_row(line: str) -> List[str]:
    """Split a Markdown pipe row into trimmed cells, dropping leading
    and trailing empties produced by ``| a | b |``."""
    cells = [c.strip() for c in line.split("|")]
    if cells and cells[0] == "":
        cells = cells[1:]
    if cells and cells[-1] == "":
        cells = cells[:-1]
    return cells


def _is_separator(line: str) -> bool:
    """A separator row is ``| --- | --- |`` (any width of dashes)."""
    cells = _split_row(line)
    return bool(cells) and all(re.fullmatch(r":?-+:?", c) for c in cells)


def parse_audit_markdown(path: pathlib.Path) -> List[dict]:
    """Parse the audit file and return one dict per kernel row.

    Each dict carries the eight :data:`AUDIT_COLUMNS` keys; missing
    columns default to ``""``. The function locates the first table
    whose header contains both a ``Kernel`` column and a ``DaCe ...
    status`` column, then ingests every contiguous row that follows the
    separator until the table ends (blank line or non-pipe row).

    Raises :class:`ValueError` if no audit table is found in ``path``.
    """
    text = pathlib.Path(path).read_text()
    lines = text.splitlines()
    header_idx = _find_audit_header(lines)
    if header_idx is None:
        raise ValueError(f"no parallelization-audit table found in {path}")

    headers = [_normalise_header(c) for c in _split_row(lines[header_idx])]
    keys: List[str] = []
    for h in headers:
        keys.append(_HEADER_TO_KEY.get(h, h.replace(" ", "_") or "col"))

    # Step past the separator row.
    cursor = header_idx + 1
    if cursor < len(lines) and _is_separator(lines[cursor]):
        cursor += 1

    rows: List[dict] = []
    while cursor < len(lines):
        line = lines[cursor]
        if not line.strip() or line.lstrip().startswith("#"):
            break
        if "|" not in line:
            break
        cells = _split_row(line)
        if len(cells) < 2 or _is_separator(line):
            break
        # Always materialise every canonical key, even if the table is shorter.
        row = {col: "" for col in AUDIT_COLUMNS}
        for k, v in zip(keys, cells):
            if k in AUDIT_COLUMNS:
                row[k] = v
        if row["name"]:
            rows.append(row)
        cursor += 1
    return rows


def _find_audit_header(lines: List[str]) -> int | None:
    for i, line in enumerate(lines):
        if "|" not in line:
            continue
        headers = [_normalise_header(c) for c in _split_row(line)]
        if "kernel" in headers and any(h.startswith("dace") for h in headers):
            # Confirm the next non-empty line is a separator -- guards
            # against false positives in prose.
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and _is_separator(lines[j]):
                return i
    return None
