#!/usr/bin/env python3
"""
Split a DaCe TSVC Python test file into one folder per kernel with
_d, _f, _d_single, _f_single variants.

_d / _f                : double / float, original iteration loop
_d_single / _f_single  : same but outer nl-loop removed (single invocation)

Output structure:
    tsvc_dace_microkernels/
        s000/
            s000_d.py
            s000_f.py
            s000_d_single.py
            s000_f_single.py

Usage:
    python split_dace_kernels.py -i tsvc_dace_kernels.py [-o tsvc_dace_microkernels]
"""

import argparse
import ast
import re
from pathlib import Path


# == 1.  Extract @dace.program functions via AST ============================


def _is_dace_program(node: ast.FunctionDef) -> bool:
    for d in node.decorator_list:
        if isinstance(d, ast.Attribute) and d.attr == "program":
            return True
        if isinstance(d, ast.Name) and d.id == "program":
            return True
    return False


def _decorator_start(node: ast.FunctionDef) -> int:
    if node.decorator_list:
        return node.decorator_list[0].lineno
    return node.lineno


def extract_kernels(src: str) -> dict[str, str]:
    """
    Return {base_name: source_text} for every @dace.program function.
    For duplicates, the LAST definition wins.
    """
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    kernels: dict[str, str] = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef) and _is_dace_program(node):
            start = _decorator_start(node) - 1
            end = node.end_lineno
            func_src = "".join(lines[start:end])
            base = node.name.removeprefix("dace_")
            kernels[base] = func_src
    return kernels


# == 2.  Detect which symbols a kernel uses ================================

ALL_SYMBOLS = {
    "LEN_1D": 'LEN_1D = dace.symbol("LEN_1D")',
    "LEN_2D": 'LEN_2D = dace.symbol("LEN_2D")',
    "ITERATIONS": 'ITERATIONS = dace.symbol("ITERATIONS")',
    "VLEN": "VLEN = 8",
    "S": "S = dace.symbol('S')",
}


def needed_symbols(func_src: str, exclude: set[str] | None = None) -> list[str]:
    """Return symbol declaration lines for symbols referenced in func_src."""
    exclude = exclude or set()
    decls = []
    for sym, decl in ALL_SYMBOLS.items():
        if sym in exclude:
            continue
        if re.search(rf"\b{sym}\b", func_src):
            decls.append(decl)
    return decls


# == 3.  Generate _d and _f variants =======================================


def make_variant(func_src: str, base: str, suffix: str) -> str:
    """
    Transform a @dace.program function source.
    suffix contains "d": keep float64     suffix contains "f": float64->float32
    Rename function: dace_<base> -> <base><suffix>
    """
    out = func_src
    out = re.sub(rf"\bdace_{re.escape(base)}\b", f"{base}{suffix}", out)

    if "_f" in suffix:
        out = re.sub(r"\bdace\.float64\b", "dace.float32", out)
        out = re.sub(r"\bnp\.float64\b", "np.float32", out)

    return out


# == 4.  Strip outer iteration loop =========================================


def strip_outer_loop_python(func_src: str) -> str:
    """Remove `for nl in range(...):` and de-indent its body by one level.

    Also removes any preceding `outer = ...` assignment that feeds into it.
    """
    lines = func_src.split("\n")
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()

        # Remove `outer = EXPR` line (only if it's a simple assignment to outer)
        if re.match(r"\s+outer\s*=\s*.+", line) and "for" not in line:
            i += 1
            continue

        # Detect `for nl in range(...):`
        if re.match(r"for\s+nl\s+in\s+range\(.*\)\s*:", stripped):
            nl_indent = len(line) - len(stripped)
            body_indent = nl_indent + 4  # one indent level deeper
            i += 1
            # Collect all lines indented deeper than the for-nl line
            while i < len(lines):
                if lines[i].strip() == "":
                    out.append("")
                    i += 1
                    continue
                cur_indent = len(lines[i]) - len(lines[i].lstrip())
                if cur_indent <= nl_indent and lines[i].strip():
                    break
                # De-indent by one level (4 spaces)
                if lines[i].startswith(" " * body_indent):
                    out.append(" " * nl_indent + lines[i][body_indent:])
                else:
                    out.append(lines[i])
                i += 1
        else:
            out.append(line)
            i += 1

    return "\n".join(out)


# == 5.  Emit files ========================================================

HEADER_TEMPLATE = """\
import dace
import numpy as np
from math import sin, cos, log, exp, pow

{symbols}

"""


def write_kernel_file(
    base: str,
    suffix: str,
    func_src: str,
    out_dir: Path,
    single_iter: bool = False,
):
    src = func_src

    if single_iter:
        src = strip_outer_loop_python(src)

    variant_src = make_variant(src, base, suffix)

    # For single-iter variants, ITERATIONS is no longer referenced
    exclude_syms = {"ITERATIONS"} if single_iter else set()
    # But check if ITERATIONS appears elsewhere in the body (rare but possible)
    if single_iter and re.search(r"\bITERATIONS\b", variant_src):
        exclude_syms = set()  # still needed

    symbols = needed_symbols(variant_src, exclude=exclude_syms)
    header = HEADER_TEMPLATE.format(symbols="\n".join(symbols))

    folder = out_dir / base
    folder.mkdir(parents=True, exist_ok=True)
    out_path = folder / f"{base}{suffix}.py"
    with open(out_path, "w") as f:
        f.write(header)
        f.write(variant_src)
        f.write("\n")


# == main ===================================================================


def main():
    ap = argparse.ArgumentParser(
        description="Split DaCe TSVC kernels into per-kernel _d/_f/_d_single/_f_single files."
    )
    ap.add_argument(
        "-i", "--input", default="tsvc2_core.py", help="Path to the Python kernels file"
    )
    ap.add_argument(
        "-o",
        "--out-dir",
        default="tsvc_dace_microkernels",
        help="Output directory (default: tsvc_dace_microkernels/)",
    )
    args = ap.parse_args()

    src = Path(args.input).read_text()
    kernels = extract_kernels(src)

    out_dir = Path(args.out_dir)

    for base, func_src in kernels.items():
        write_kernel_file(base, "_d", func_src, out_dir, single_iter=False)
        write_kernel_file(base, "_f", func_src, out_dir, single_iter=False)
        write_kernel_file(base, "_d_single", func_src, out_dir, single_iter=True)
        write_kernel_file(base, "_f_single", func_src, out_dir, single_iter=True)

    n = len(kernels)
    print(f"Wrote {n} kernels x 4 variants = {n * 4} files")
    print(f"Structure: {out_dir}/<kernel>/<kernel>_{{d,f,d_single,f_single}}.py")


if __name__ == "__main__":
    main()