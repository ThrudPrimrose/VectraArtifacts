#!/usr/bin/env python3
"""
Split tsvcpp.cpp into one folder per kernel with _d and _f variants.

Output structure:
    tsvc_microkernels/
        s000/
            s000_d.cpp    (double, __restrict__)
            s000_f.cpp    (float,  __restrict__)
        s111/
            ...

Usage:
    python split_kernels.py tsvcpp.cpp [-o tsvc_microkernels]
"""

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path


# == 1.  Parse top-level constructs ==========================================

@dataclass
class TopLevel:
    kind: str          # "function" | "comment" | "preamble"
    name: str = ""
    lines: list[str] = field(default_factory=list)
    start: int = 0
    end:   int = 0


def parse_toplevel(src_lines: list[str]) -> list[TopLevel]:
    blocks: list[TopLevel] = []
    i = 0
    n = len(src_lines)

    preamble_lines: list[str] = []
    while i < n:
        line = src_lines[i]
        if re.match(r'^(void|double|int|float|static)\s+\w+\s*\(', line):
            break
        preamble_lines.append(line)
        i += 1
    if preamble_lines:
        blocks.append(TopLevel("preamble", "__preamble__", preamble_lines, 0, i - 1))

    while i < n:
        line = src_lines[i]

        if line.strip() == "" or line.strip().startswith("//"):
            comment_start = i
            comment_lines: list[str] = []
            while i < n and (src_lines[i].strip() == "" or src_lines[i].strip().startswith("//")):
                comment_lines.append(src_lines[i])
                i += 1
            blocks.append(TopLevel("comment", "", comment_lines, comment_start, i - 1))
            continue

        m = re.match(r'^(?:static\s+(?:inline\s+)?)?(?:void|double|int|float)\s+(\w+)\s*\(', line)
        if m:
            fname = m.group(1)
            func_start = i
            func_lines: list[str] = []
            depth = 0
            found_open = False
            while i < n:
                func_lines.append(src_lines[i])
                depth += src_lines[i].count("{") - src_lines[i].count("}")
                if "{" in src_lines[i]:
                    found_open = True
                i += 1
                if found_open and depth <= 0:
                    break
            blocks.append(TopLevel("function", fname, func_lines, func_start, i - 1))
            continue

        i += 1

    return blocks


# == 2.  Group helpers with their kernel =====================================

def group_kernels(blocks: list[TopLevel]) -> dict[str, list[TopLevel]]:
    kernels: dict[str, list[TopLevel]] = {}
    pending: list[TopLevel] = []

    for b in blocks:
        if b.kind == "preamble":
            continue
        if b.kind == "function" and b.name.endswith("_run_timed"):
            base = b.name.removesuffix("_run_timed")
            kernels[base] = pending + [b]
            pending = []
        else:
            pending.append(b)

    return kernels


# == 3.  Resolve cross-references for helpers ================================

def find_helper_defs(blocks: list[TopLevel]) -> dict[str, TopLevel]:
    helpers: dict[str, TopLevel] = {}
    for b in blocks:
        if b.kind == "function" and not b.name.endswith("_run_timed"):
            helpers[b.name] = b
    return helpers


def kernel_calls_helper(kernel_blocks: list[TopLevel], helper_name: str) -> bool:
    for b in kernel_blocks:
        if b.kind != "function":
            continue
        body = "".join(b.lines)
        if b.name != helper_name and re.search(rf'\b{re.escape(helper_name)}\s*\(', body):
            return True
    return False


# == 4.  Transformations =====================================================

def add_restrict(text: str) -> str:
    """Add __restrict__ to pointer declarations (type *name), not to a * b."""
    TYPE_PATTERN = r'(?:double|float|int|void|char|\w+_t)'

    out_lines = []
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("//"):
            out_lines.append(line)
            continue
        line = re.sub(
            rf'({TYPE_PATTERN})\s*\*\s*(?!__restrict__)(\w)',
            r'\1 * __restrict__ \2',
            line,
        )
        out_lines.append(line)
    return "".join(out_lines)


def to_float_variant(text: str) -> str:
    """Convert a double-precision kernel body to single-precision."""
    out = re.sub(r'\bdouble\b', 'float', text)
    out = re.sub(
        r'(?<![.\w])(\d+\.\d*|\.\d+)(?![fFdDeE\w])',
        r'\1f',
        out,
    )
    return out


def collect_function_names(body: str) -> list[str]:
    """Find all function names defined in the body text."""
    return re.findall(
        r'^(?:static\s+(?:inline\s+)?)?(?:void|double|int|float)\s+(\w+)\s*\(',
        body,
        re.MULTILINE,
    )


def rename_functions(body: str, suffix: str, func_names: list[str]) -> str:
    """Rename every function in func_names (definitions + call sites) with suffix."""
    # Sort longest-first to avoid partial replacement (e.g. s471 before s471s)
    for name in sorted(func_names, key=len, reverse=True):
        # Rename all occurrences: definitions and calls
        body = re.sub(rf'\b{re.escape(name)}\b', f'{name}{suffix}', body)
    return body


# == 5.  Assemble and emit ==================================================

HEADER_TEMPLATE = """\
#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {{

{body}

}} // extern "C"
"""


def build_body(
    base: str,
    parts: list[TopLevel],
    helper_defs: dict[str, TopLevel],
) -> str:
    body_lines: list[str] = []

    # The main kernel is the _run_timed function (last function in parts).
    main_func = base + "_run_timed"

    # Identify which helper functions in `parts` are actually called by
    # the main kernel (or by other called helpers).  The pending-block
    # grouping can attach unrelated helpers that appeared between kernels.
    local_helpers = [b for b in parts if b.kind == "function" and b.name != main_func]
    needed_locals = set()
    for h in local_helpers:
        if kernel_calls_helper(parts, h.name):
            needed_locals.add(h.name)

    # External helpers (defined elsewhere, called by this kernel)
    names_in_parts = {b.name for b in parts if b.kind == "function"}
    for hname, hblock in helper_defs.items():
        if hname in names_in_parts:
            continue
        if kernel_calls_helper(parts, hname):
            body_lines.extend(hblock.lines)
            body_lines.append("\n")

    # Emit parts, skipping uncalled local helpers (and their preceding comments)
    for b in parts:
        if b.kind == "function" and b.name != main_func and b.name not in needed_locals:
            continue
        body_lines.extend(b.lines)

    body = "".join(body_lines)
    body = body.replace(f"{base}_run_timed", base)
    return body


def write_variant(body: str, base: str, suffix: str, out_dir: Path):
    variant_body = body

    # Find ALL function names defined in this variant
    func_names = collect_function_names(variant_body)

    # Rename every function (definition + call sites) with _d or _f suffix
    variant_body = rename_functions(variant_body, suffix, func_names)

    # Float conversion
    if suffix == "_f":
        variant_body = to_float_variant(variant_body)

    # Add __restrict__ to pointer declarations
    variant_body = add_restrict(variant_body)

    folder = out_dir / base
    folder.mkdir(parents=True, exist_ok=True)
    out_path = folder / f"{base}{suffix}.cpp"
    with open(out_path, "w") as f:
        f.write(HEADER_TEMPLATE.format(body=variant_body.strip()))


# == main ====================================================================

def main():
    ap = argparse.ArgumentParser(
        description="Split tsvcpp.cpp into per-kernel folders with _d/_f variants.")
    ap.add_argument("-i", "--input", default="tsvc2_core.cpp", help="Path to tsvcpp.cpp")
    ap.add_argument("-o", "--out-dir", default="tsvc_cpp_microkernels",
                    help="Output directory (default: tsvc_cpp_microkernels/)")
    args = ap.parse_args()

    src = Path(args.input).read_text()
    src_lines = src.splitlines(keepends=True)

    blocks = parse_toplevel(src_lines)
    kernels = group_kernels(blocks)
    helper_defs = find_helper_defs(blocks)

    out_dir = Path(args.out_dir)

    for base, parts in kernels.items():
        body = build_body(base, parts, helper_defs)
        write_variant(body, base, "_d", out_dir)
        write_variant(body, base, "_f", out_dir)

    n = len(kernels)
    print(f"Wrote {n} kernels x 2 variants = {n*2} files to {out_dir}/")
    print(f"Structure: {out_dir}/<kernel>/<kernel>_d.cpp")
    print(f"           {out_dir}/<kernel>/<kernel>_f.cpp")


if __name__ == "__main__":
    main()