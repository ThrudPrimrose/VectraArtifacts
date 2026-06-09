"""Split a monolithic TSVC-shaped C++ file into per-kernel folders.

The input has one ``void <kernel>_run_timed(...)`` function per kernel
plus optional ``static`` helper functions and ``//`` comment blocks
between them. We emit one folder per kernel containing a ``_d``
(double) and ``_f`` (float) variant; each variant has ``__restrict__``
added on pointer declarations.

``tsvc_2`` carries an outer ``for (int nl = 0; ...; nl++)`` benchmark
repeat loop and wants ``_single`` siblings that strip it (matching the
``_d_single`` / ``_f_single`` files :func:`split_dace.split_dace`
emits); ``tsvc_2_5`` does not. The ``emit_single`` toggle selects
between the two variant sets.

Shared by ``tsvc_2`` and ``tsvc_2_5``; the per-corpus scripts only
override the default input + output paths via :func:`main_split_cpp`.
"""
import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

HEADER_TEMPLATE = """\
#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {{

{body}

}} // extern "C"
"""

_FUNC_DEF_RE = re.compile(r'^(?:static\s+(?:inline\s+)?)?(?:void|double|int|float)\s+(\w+)\s*\(', re.MULTILINE)
_TYPE_PATTERN = r'(?:double|float|int|void|char|\w+_t)'
_RESTRICT_RE = re.compile(rf'({_TYPE_PATTERN})\s*\*\s*(?!__restrict__)(\w)')
_FLOAT_LITERAL_RE = re.compile(r'(?<![.\w])(\d+\.\d*|\.\d+)(?![fFdDeE\w])')
_NL_LOOP_RE = re.compile(r'^\s*for\s*\(\s*int\s+nl\b')
#: In-body ``using clock = std::chrono::high_resolution_clock;`` alias
#: that some kernels declare locally; redundant with the header's
#: ``clock_highres`` and stripped so every kernel uses the one alias.
_LOCAL_CLOCK_ALIAS_RE = re.compile(r'^\s*using\s+clock\s*=\s*std::chrono::high_resolution_clock\s*;\s*$')
_CLOCK_USE_RE = re.compile(r'\bclock::')


@dataclass
class _TopLevel:
    kind: str  # "function" | "comment" | "preamble"
    name: str = ""
    lines: List[str] = field(default_factory=list)


def _parse_toplevel(src_lines: List[str]) -> List[_TopLevel]:
    """Walk the source linearly, classifying each top-level run as a
    preamble line block, a comment / blank-line block, or a complete
    C function body (preserving brace depth)."""
    blocks: List[_TopLevel] = []
    i, n = 0, len(src_lines)

    preamble: List[str] = []
    while i < n and not re.match(r'^(void|double|int|float|static)\s+\w+\s*\(', src_lines[i]):
        preamble.append(src_lines[i])
        i += 1
    if preamble:
        blocks.append(_TopLevel("preamble", "__preamble__", preamble))

    while i < n:
        line = src_lines[i]
        stripped = line.strip()

        if stripped == "" or stripped.startswith("//"):
            chunk: List[str] = []
            while i < n and (src_lines[i].strip() == "" or src_lines[i].strip().startswith("//")):
                chunk.append(src_lines[i])
                i += 1
            blocks.append(_TopLevel("comment", "", chunk))
            continue

        m = _FUNC_DEF_RE.match(line)
        if m:
            fname = m.group(1)
            chunk = []
            depth = 0
            found_open = False
            while i < n:
                chunk.append(src_lines[i])
                depth += src_lines[i].count("{") - src_lines[i].count("}")
                if "{" in src_lines[i]:
                    found_open = True
                i += 1
                if found_open and depth <= 0:
                    break
            blocks.append(_TopLevel("function", fname, chunk))
            continue

        i += 1
    return blocks


def _group_kernels(blocks: List[_TopLevel]) -> Dict[str, List[_TopLevel]]:
    """Sweep blocks left-to-right; the trailing ``..._run_timed``
    function ends each kernel group, absorbing any preceding comments
    or helpers as part of that group."""
    kernels: Dict[str, List[_TopLevel]] = {}
    pending: List[_TopLevel] = []
    for b in blocks:
        if b.kind == "preamble":
            continue
        if b.kind == "function" and b.name.endswith("_run_timed"):
            kernels[b.name.removesuffix("_run_timed")] = pending + [b]
            pending = []
        else:
            pending.append(b)
    return kernels


def _find_helper_defs(blocks: List[_TopLevel]) -> Dict[str, _TopLevel]:
    """All non-``_run_timed`` functions visible anywhere in the source;
    these get inlined into a kernel folder only when the kernel
    actually calls them."""
    return {b.name: b for b in blocks if b.kind == "function" and not b.name.endswith("_run_timed")}


def _kernel_calls_helper(parts: List[_TopLevel], helper_name: str) -> bool:
    pat = re.compile(rf'\b{re.escape(helper_name)}\s*\(')
    for b in parts:
        if b.kind != "function" or b.name == helper_name:
            continue
        if pat.search("".join(b.lines)):
            return True
    return False


def _add_restrict(text: str) -> str:
    """Insert ``__restrict__`` between pointer types and pointer names.
    Skips comment lines to avoid clobbering documentation."""
    out: List[str] = []
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("//"):
            out.append(line)
        else:
            out.append(_RESTRICT_RE.sub(r'\1 * __restrict__ \2', line))
    return "".join(out)


def _to_float(text: str) -> str:
    """Convert ``double`` -> ``float`` and float literals to their
    ``f``-suffixed form (``0.1`` -> ``0.1f``)."""
    out = re.sub(r'\bdouble\b', 'float', text)
    return _FLOAT_LITERAL_RE.sub(r'\1f', out)


def _normalize_clock(body: str) -> str:
    """Drop any in-body ``using clock = std::chrono::high_resolution_clock;``
    alias and rewrite its ``clock::`` uses to the header-level
    ``clock_highres`` alias, so the clock type is declared once (in the
    file header) rather than re-aliased inside the kernel body."""
    out = [ln for ln in body.split("\n") if not _LOCAL_CLOCK_ALIAS_RE.match(ln)]
    return _CLOCK_USE_RE.sub("clock_highres::", "\n".join(out))


def _strip_outer_nl_loop(body: str) -> str:
    """Remove the outer ``for (int nl = 0; ...; nl++) { ... }`` benchmark
    repeat loop and de-indent its body one level, leaving the timing
    wrapper and signature intact.

    Produces the single-invocation ``_single`` variant; mirrors
    :func:`split_dace._strip_outer_nl_loop`. The matching close brace is
    located by brace-depth counting so nested loops inside the body are
    preserved."""
    lines = body.split("\n")
    out: List[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if _NL_LOOP_RE.match(line):
            nl_indent = len(line) - len(line.lstrip())
            depth = line.count("{") - line.count("}")
            i += 1
            body_lines: List[str] = []
            while i < n and depth > 0:
                depth += lines[i].count("{") - lines[i].count("}")
                if depth <= 0:
                    i += 1  # drop the line carrying the matching close brace
                    break
                body_lines.append(lines[i])
                i += 1
            first = next((bl for bl in body_lines if bl.strip()), "")
            shift = max(0, (len(first) - len(first.lstrip())) - nl_indent)
            for bl in body_lines:
                if not bl.strip():
                    out.append("")
                elif not bl[:shift].strip():
                    out.append(bl[shift:])
                else:
                    out.append(bl.lstrip())
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def _collect_function_names(body: str) -> List[str]:
    return _FUNC_DEF_RE.findall(body)


def _rename_functions(body: str, suffix: str, names: List[str]) -> str:
    """Rename every function in ``names`` (definitions + call sites)
    by appending ``suffix``. Longest-first so ``s471`` doesn't rename
    inside ``s471s``."""
    for name in sorted(names, key=len, reverse=True):
        body = re.sub(rf'\b{re.escape(name)}\b', f'{name}{suffix}', body)
    return body


def _build_body(base: str, parts: List[_TopLevel], helper_defs: Dict[str, _TopLevel]) -> str:
    """Assemble one kernel's body: external helpers it actually calls,
    then its own local pending blocks (sans uncalled helpers), with
    the ``_run_timed`` suffix stripped so the kernel exports as
    ``<base>`` directly."""
    main_func = base + "_run_timed"
    local_helpers = [b for b in parts if b.kind == "function" and b.name != main_func]
    needed_locals = {h.name for h in local_helpers if _kernel_calls_helper(parts, h.name)}

    body_lines: List[str] = []
    names_in_parts = {b.name for b in parts if b.kind == "function"}
    for hname, hblock in helper_defs.items():
        if hname in names_in_parts:
            continue
        if _kernel_calls_helper(parts, hname):
            body_lines.extend(hblock.lines)
            body_lines.append("\n")
    for b in parts:
        if b.kind == "function" and b.name != main_func and b.name not in needed_locals:
            continue
        body_lines.extend(b.lines)
    return _normalize_clock("".join(body_lines).replace(main_func, base))


def _write_variant(body: str, base: str, suffix: str, out_dir: Path, single: bool = False) -> Path:
    """Write one ``<base><suffix>.cpp`` file. Strips the outer ``nl``
    repeat loop for ``_single`` variants, renames every defined function
    with ``suffix``, downgrades to ``float`` for the ``_f`` variants, and
    adds ``__restrict__`` on pointer declarations."""
    if single:
        body = _strip_outer_nl_loop(body)
    func_names = _collect_function_names(body)
    variant = _rename_functions(body, suffix, func_names)
    if "_f" in suffix:
        variant = _to_float(variant)
    variant = _add_restrict(variant)

    folder = out_dir / base
    folder.mkdir(parents=True, exist_ok=True)
    out_path = folder / f"{base}{suffix}.cpp"
    out_path.write_text(HEADER_TEMPLATE.format(body=variant.strip()))
    return out_path


def split_cpp(input_path: Path, out_dir: Path, *, emit_single: bool = False) -> int:
    """Split ``input_path`` into ``out_dir/<kernel>/<kernel>_{d,f}.cpp``.

    :param input_path: monolithic ``<corpus>_core.cpp`` source.
    :param out_dir: per-kernel folder root; created if missing.
    :param emit_single: also emit ``_d_single`` / ``_f_single`` siblings
        with the outer ``for (int nl = 0; ...; nl++)`` repeat loop
        removed. Required by tsvc_2's single-invocation benchmark.
    :returns: number of kernel groups written (one per ``_run_timed``
              function in the input).
    """
    src_lines = Path(input_path).read_text().splitlines(keepends=True)
    blocks = _parse_toplevel(src_lines)
    kernels = _group_kernels(blocks)
    helper_defs = _find_helper_defs(blocks)

    out_dir = Path(out_dir)
    for base, parts in kernels.items():
        body = _build_body(base, parts, helper_defs)
        _write_variant(body, base, "_d", out_dir)
        _write_variant(body, base, "_f", out_dir)
        if emit_single:
            _write_variant(body, base, "_d_single", out_dir, single=True)
            _write_variant(body, base, "_f_single", out_dir, single=True)
    return len(kernels)


def main_split_cpp(
    default_input: str,
    default_out_dir: str,
    *,
    emit_single: bool = False,
    argv: "list | None" = None,
) -> int:
    """Argparse wrapper used by ``tsvc_2/`` and ``tsvc_2_5/`` entry
    points. ``default_input`` + ``default_out_dir`` are the corpus's
    own conventional paths."""
    ap = argparse.ArgumentParser(description="Split a TSVC-shaped core.cpp into per-kernel _d/_f variants.")
    ap.add_argument("-i", "--input", default=default_input, help="Path to the monolithic core .cpp source.")
    ap.add_argument("-o", "--out-dir", default=default_out_dir, help="Output directory for per-kernel folders.")
    args = ap.parse_args(argv)
    n = split_cpp(Path(args.input), Path(args.out_dir), emit_single=emit_single)
    variants = 4 if emit_single else 2
    print(f"Wrote {n} kernels x {variants} variants = {n * variants} files to {args.out_dir}/")
    return 0
