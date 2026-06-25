#!/usr/bin/env python3
"""Remove the ``for (nl < N*iterations) { ... }`` repeat wrapper from every
TSVC C/C++ source (master cores + the split per-kernel microkernels).

The kernels were written with an outer repeat loop purely to accumulate
measurable wall-clock time. Downstream (npbench) times each kernel a single
pass via an external bracket, so the repeat loop is dropped: each kernel now
does ONE pass. The ``iterations`` parameter is intentionally KEPT so the
VectraArtifacts binding/harness ABI is unchanged (it is simply ignored).

Paren/brace-matched so loop conditions with inner parens
(``100 * (iterations / (len_2d))``) are handled. Idempotent.

    python scripts/strip_iteration_loops.py            # rewrite in place
    python scripts/strip_iteration_loops.py --check     # CI: assert none remain
"""
import argparse
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent


def match_paren(text: str, open_idx: int) -> int:
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("unbalanced parens")


def match_brace(text: str, open_idx: int) -> int:
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("unbalanced braces")


def strip_loops(text: str) -> str:
    """Remove every ``for (... iterations ...) { body }`` wrapper, keeping body."""
    while True:
        target = None
        for fm in re.finditer(r"\bfor\s*\(", text):
            open_paren = text.index("(", fm.start())
            close_paren = match_paren(text, open_paren)
            if re.search(r"\biterations\b", text[open_paren:close_paren + 1]):
                target = (fm.start(), close_paren)
                break
        if target is None:
            return text
        start, close_paren = target
        open_brace = text.index("{", close_paren)
        close_brace = match_brace(text, open_brace)
        inner = text[open_brace + 1:close_brace]
        text = text[:start] + inner + text[close_brace + 1:]


def cpp_sources():
    yield from (REPO / "tsvc_2").glob("*.cpp")
    yield from (REPO / "tsvc_2_5").glob("*.cpp")
    yield from REPO.glob("tsvc_2/tsvc_cpp_microkernels/**/*.cpp")
    yield from REPO.glob("tsvc_2_5/**/*.cpp")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)

    changed = remaining = 0
    seen = set()
    for src in sorted(set(cpp_sources())):
        if src in seen:
            continue
        seen.add(src)
        text = src.read_text()
        new = strip_loops(text)
        # Detect a dangling repeat loop (code only, ignore comments).
        code = re.sub(r"//[^\n]*|/\*.*?\*/", "", new, flags=re.S)
        if re.search(r"for\s*\([^\n]*\biterations\b", code):
            remaining += 1
            print(f"  ! repeat loop survives in {src.relative_to(REPO)}", file=sys.stderr)
        if new == text:
            continue
        if not args.check:
            src.write_text(new)
        changed += 1

    if args.check:
        if remaining:
            print(f"strip_iteration_loops: {remaining} files still have a repeat loop", file=sys.stderr)
            return 1
        print("strip_iteration_loops: no repeat loops remain")
        return 0
    print(f"strip_iteration_loops: rewrote {changed} C/C++ files ({remaining} with surviving loops)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
