"""Split a monolithic DaCe-Python corpus into per-kernel files.

Walks the input via ``ast`` to extract every ``@dace.program``,
rewrites the function name to ``<base>_{d,f}``, flips ``float64`` ->
``float32`` for the ``_f`` variant, and emits a small per-file header
declaring only the ``dace.symbol`` constants the kernel actually
references.

``tsvc_2`` carries an outer ``for nl in range(ITERATIONS)`` benchmark
loop and wants ``_single`` siblings that strip it; ``tsvc_2_5`` does
not. The ``emit_single`` toggle selects between the two variant sets.
"""
import argparse
import ast
import re
from pathlib import Path
from typing import Dict, Iterable, List, Set

#: Every symbol the corpora may reference. Declarations are emitted in
#: this dict's iteration order so a kernel that uses ``LEN_1D`` and ``K``
#: gets them in a predictable order in its file.
DEFAULT_SYMBOLS: Dict[str, str] = {
    "LEN_1D": 'LEN_1D = dace.symbol("LEN_1D")',
    "LEN_2D": 'LEN_2D = dace.symbol("LEN_2D")',
    "LEN_3D": 'LEN_3D = dace.symbol("LEN_3D")',
    "ITERATIONS": 'ITERATIONS = dace.symbol("ITERATIONS")',
    "VLEN": "VLEN = 8",
    "S": 'S = dace.symbol("S")',
    "SSYM": 'SSYM = dace.symbol("SSYM")',
    "K": 'K = dace.symbol("K")',
    "M": 'M = dace.symbol("M")',
    "T": 'T = dace.symbol("T")',
    "T1": 'T1 = dace.symbol("T1")',
    "T2": 'T2 = dace.symbol("T2")',
}

HEADER_TEMPLATE_PLAIN = """\
import dace
import numpy as np
from math import sin, cos, log, exp, pow

{symbols}

"""

HEADER_TEMPLATE_WITH_MATHEXTRAS = """\
from math import sqrt, exp

import dace
import numpy as np

{symbols}

"""


def _is_dace_program(node: ast.FunctionDef) -> bool:
    for d in node.decorator_list:
        if isinstance(d, ast.Attribute) and d.attr == "program":
            return True
        if isinstance(d, ast.Name) and d.id == "program":
            return True
    return False


def _decorator_start(node: ast.FunctionDef) -> int:
    return node.decorator_list[0].lineno if node.decorator_list else node.lineno


def _extract_kernels(src: str, strip_prefix: str) -> Dict[str, str]:
    """Return ``{base_name: source_text}`` for every ``@dace.program``
    in ``src``. ``strip_prefix`` ("dace_" for tsvc_2, "" for tsvc_2_5)
    is removed from the function name to form the base."""
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    out: Dict[str, str] = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef) and _is_dace_program(node):
            start = _decorator_start(node) - 1
            end = node.end_lineno
            base = node.name.removeprefix(strip_prefix) if strip_prefix else node.name
            out[base] = "".join(lines[start:end])
    return out


def _needed_symbols(func_src: str, symbol_table: Dict[str, str], exclude: "Set[str] | None" = None) -> List[str]:
    exclude = exclude or set()
    decls: List[str] = []
    for sym, decl in symbol_table.items():
        if sym in exclude:
            continue
        if re.search(rf"\b{sym}\b", func_src):
            decls.append(decl)
    return decls


def _make_variant(func_src: str, base: str, suffix: str, source_prefix: str) -> str:
    """Rename ``<source_prefix><base>`` -> ``<base><suffix>`` (the
    source prefix matches the ``strip_prefix`` used during extraction)
    and flip ``float64`` -> ``float32`` for the float variant."""
    if source_prefix:
        out = re.sub(rf"\b{re.escape(source_prefix)}{re.escape(base)}\b", f"{base}{suffix}", func_src)
    else:
        out = re.sub(rf"\b{re.escape(base)}\b", f"{base}{suffix}", func_src)
    if "_f" in suffix:
        out = re.sub(r"\bdace\.float64\b", "dace.float32", out)
        out = re.sub(r"\bnp\.float64\b", "np.float32", out)
    return out


def _strip_outer_nl_loop(func_src: str) -> str:
    """Drop ``for nl in range(...)`` outer iteration loop + de-indent
    its body by one level, plus any preceding ``outer = EXPR`` assign.

    Used by the ``_d_single`` / ``_f_single`` variants the TSVC-2
    corpus emits for single-invocation kernels."""
    lines = func_src.split("\n")
    out: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if re.match(r"\s+outer\s*=\s*.+", line) and "for" not in line:
            i += 1
            continue
        if re.match(r"for\s+nl\s+in\s+range\(.*\)\s*:", stripped):
            nl_indent = len(line) - len(stripped)
            body_indent = nl_indent + 4
            i += 1
            while i < len(lines):
                if lines[i].strip() == "":
                    out.append("")
                    i += 1
                    continue
                cur_indent = len(lines[i]) - len(lines[i].lstrip())
                if cur_indent <= nl_indent and lines[i].strip():
                    break
                if lines[i].startswith(" " * body_indent):
                    out.append(" " * nl_indent + lines[i][body_indent:])
                else:
                    out.append(lines[i])
                i += 1
        else:
            out.append(line)
            i += 1
    return "\n".join(out)


def _select_header(func_src: str) -> str:
    """Pick the import header that matches what the kernel needs.
    Kernels that use ``sqrt`` / ``exp`` get the extension-style
    header; the legacy TSVC-2 kernels keep the wider ``sin/cos/log``
    set."""
    if "sqrt(" in func_src or "exp(" in func_src or re.search(r"\bmath\.sqrt|math\.exp", func_src):
        return HEADER_TEMPLATE_WITH_MATHEXTRAS
    return HEADER_TEMPLATE_PLAIN


def _write_variant(
    base: str,
    suffix: str,
    func_src: str,
    out_dir: Path,
    symbol_table: Dict[str, str],
    source_prefix: str,
    single_iter: bool,
) -> Path:
    src = _strip_outer_nl_loop(func_src) if single_iter else func_src
    variant_src = _make_variant(src, base, suffix, source_prefix)

    exclude: Set[str] = set()
    if single_iter and not re.search(r"\bITERATIONS\b", variant_src):
        exclude = {"ITERATIONS"}
    symbols = _needed_symbols(variant_src, symbol_table, exclude=exclude)
    header = _select_header(variant_src).format(symbols="\n".join(symbols))

    folder = out_dir / base
    folder.mkdir(parents=True, exist_ok=True)
    out_path = folder / f"{base}{suffix}.py"
    out_path.write_text(header + variant_src + "\n")
    return out_path


def split_dace(
    input_path: Path,
    out_dir: Path,
    *,
    source_prefix: str = "",
    emit_single: bool = False,
    symbol_table: "Dict[str, str] | None" = None,
) -> int:
    """Split a DaCe Python corpus into per-kernel ``_d`` / ``_f`` (and
    optional ``_d_single`` / ``_f_single``) files.

    :param input_path: monolithic ``<corpus>_core.py`` source.
    :param out_dir: per-kernel folder root; created if missing.
    :param source_prefix: name prefix to strip from each
        ``@dace.program`` function (``"dace_"`` for tsvc_2, ``""`` for
        tsvc_2_5).
    :param emit_single: also emit ``_d_single`` / ``_f_single``
        siblings with the outer ``for nl in range(ITERATIONS)`` loop
        removed. Required by tsvc_2's single-invocation benchmark.
    :param symbol_table: override the default ``dace.symbol`` table.
    :returns: number of kernels processed.
    """
    src = Path(input_path).read_text()
    kernels = _extract_kernels(src, source_prefix)
    table = symbol_table or DEFAULT_SYMBOLS
    out_dir = Path(out_dir)
    for base, func_src in kernels.items():
        _write_variant(base, "_d", func_src, out_dir, table, source_prefix, single_iter=False)
        _write_variant(base, "_f", func_src, out_dir, table, source_prefix, single_iter=False)
        if emit_single:
            _write_variant(base, "_d_single", func_src, out_dir, table, source_prefix, single_iter=True)
            _write_variant(base, "_f_single", func_src, out_dir, table, source_prefix, single_iter=True)
    return len(kernels)


def main_split_dace(
    default_input: str,
    default_out_dir: str,
    *,
    source_prefix: str = "",
    emit_single: bool = False,
    argv: "list | None" = None,
) -> int:
    """Argparse wrapper used by ``tsvc_2/`` and ``tsvc_2_5/`` entry
    points."""
    ap = argparse.ArgumentParser(description="Split a DaCe-Python corpus into per-kernel _d/_f files.")
    ap.add_argument("-i", "--input", default=default_input)
    ap.add_argument("-o", "--out-dir", default=default_out_dir)
    args = ap.parse_args(argv)
    n = split_dace(Path(args.input), Path(args.out_dir), source_prefix=source_prefix, emit_single=emit_single)
    variants = 4 if emit_single else 2
    print(f"Wrote {n} kernels x {variants} variants = {n * variants} files to {args.out_dir}/")
    return 0
