"""Audit markdown parser exercises the real ``docs/PARALLELIZATION_AUDIT.md``
file (when present) plus a synthetic minimal table."""
import pathlib

import pytest

from vectra_artifacts.tsvc_audit import AUDIT_COLUMNS, parse_audit_markdown

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
REAL_AUDIT = REPO_ROOT / "docs" / "PARALLELIZATION_AUDIT.md"


def _write_minimal(tmp_path):
    text = """\
# header

intro line

| Kernel | TSVC-2 category | Original TSVC comment | Loop shape | Parallel in principle? | Blocking factor | DaCe canonicalize status | Notes |
|---|---|---|---|---|---|---|---|
| s000 | linear | trivial copy | `for i: a[i]=b[i]+1.0` | yes | (none) | M | basic |
| s111 | linear | strided | `for i: a[i]=a[i-1]+b[i]` | yes | (none) | M | strided |

footer.
"""
    p = tmp_path / "audit.md"
    p.write_text(text)
    return p


def test_parses_minimal_table(tmp_path):
    p = _write_minimal(tmp_path)
    rows = parse_audit_markdown(p)
    assert [r["name"] for r in rows] == ["s000", "s111"]
    assert rows[0]["category"] == "linear"
    assert rows[0]["dace_status"] == "M"
    assert "trivial" in rows[0]["tsvc_comment"]
    for r in rows:
        # Every canonical column key is present.
        for col in AUDIT_COLUMNS:
            assert col in r


def test_raises_when_no_table(tmp_path):
    p = tmp_path / "no_table.md"
    p.write_text("# no tables here\n")
    with pytest.raises(ValueError):
        parse_audit_markdown(p)


@pytest.mark.skipif(not REAL_AUDIT.exists(), reason="docs/PARALLELIZATION_AUDIT.md not present yet")
def test_parses_real_audit_file():
    """The real audit file -- when present -- must parse without error
    and yield 151 rows for the TSVC-2 suite."""
    rows = parse_audit_markdown(REAL_AUDIT)
    assert len(rows) == 151
    names = [r["name"] for r in rows]
    assert "s000" in names
    assert "s111" in names
    assert "s31111" in names
