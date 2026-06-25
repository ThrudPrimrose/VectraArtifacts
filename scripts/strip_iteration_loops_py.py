#!/usr/bin/env python3
"""Remove the ``for nl in range(... ITERATIONS ...):`` repeat wrapper from the
TSVC dace/numpy kernels (master ``tsvc2_core.py`` + the split dace
microkernels), keeping the loop body (dedented one level).

Mirrors :mod:`scripts.strip_iteration_loops` for the C/C++ sources: the outer
repeat loop only existed to make wall-clock timing measurable; each kernel now
does a single pass. The splitter scripts (``split_dace*.py``) are tooling that
merely *match* the pattern and are deliberately excluded.

    python scripts/strip_iteration_loops_py.py            # rewrite in place
    python scripts/strip_iteration_loops_py.py --check     # CI: assert none remain
"""
import argparse
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
FOR_NL = re.compile(r"^(\s*)for\s+nl\s+in\s+range\([^\n]*\bITERATIONS\b[^\n]*\)\s*:\s*$")


def strip_loops(text: str) -> str:
    lines = text.splitlines(keepends=True)
    out = []
    i = 0
    while i < len(lines):
        m = FOR_NL.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        for_indent = len(m.group(1))
        i += 1  # skip the `for nl ...:` line
        body = []
        while i < len(lines):
            ln = lines[i]
            if ln.strip() == "":
                body.append(ln)
                i += 1
                continue
            indent = len(ln) - len(ln.lstrip())
            if indent <= for_indent:
                break
            body.append(ln)
            i += 1
        # Dedent the body one level (4 spaces); blanks pass through.
        for ln in body:
            out.append(ln[4:] if ln[:4] == "    " else ln)
    return "".join(out)


def py_sources():
    yield REPO / "tsvc_2" / "tsvc2_core.py"
    yield REPO / "tsvc_2_5" / "tsvc_2_5_core.py"
    yield from REPO.glob("tsvc_2/tsvc_dace_microkernels/**/*.py")
    yield from REPO.glob("tsvc_2_5/tsvc_2_5_dace_microkernels/**/*.py")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)

    changed = remaining = 0
    for src in sorted({p for p in py_sources() if p.exists()}):
        text = src.read_text()
        new = strip_loops(text)
        if FOR_NL.search(new) or re.search(r"for\s+nl\s+in\s+range\([^\n]*ITERATIONS", new):
            remaining += 1
            print(f"  ! loop survives in {src.relative_to(REPO)}", file=sys.stderr)
        if new == text:
            continue
        if not args.check:
            src.write_text(new)
        changed += 1

    if args.check:
        if remaining:
            print(f"strip_iteration_loops_py: {remaining} files still have a loop", file=sys.stderr)
            return 1
        print("strip_iteration_loops_py: no ITERATIONS loops remain")
        return 0
    print(f"strip_iteration_loops_py: rewrote {changed} py files ({remaining} with surviving loops)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
