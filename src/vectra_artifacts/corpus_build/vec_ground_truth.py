"""vec_ground_truth.py — shared assembly-based vectorization ground truth.

``compile_cpp.py`` and ``compile_dace.py`` each used to keep their own
byte-for-byte copy of this scan (SIMD-register regexes, function-label
regex, function splitter). That duplication is exactly how a bug like the
one below survives in one copy and gets fixed in the other: this module is
now the single place both import from.

Function-label matching bug (fixed here)
-----------------------------------------
The label regex used to require nothing but whitespace between the ``:``
and end-of-line (``r"...:\\s*$"``). Apple clang's ``-S`` output annotates
almost every label with a trailing comment —
``_s114_d_single:                         ; @s114_d_single`` — so on
Darwin that regex failed to match not just basic-block labels but often
the function's own entry label. Worse, ``_split_into_functions`` silently
*discarded* everything accumulated before the first label that DID
happen to match, instead of keeping it in a chunk. Combined, an entire
vectorized loop body could end up thrown away before ever reaching the
SIMD-instruction scan, producing a false "not vectorized" ground-truth
verdict — and, since the compiler's own remark correctly said
"vectorized loop", a spurious ``remark_mismatch``. (Kernel s114 on
clang/apple_m_series/default was one observed case: real NEON code —
``ldp q0, q1, ...`` / ``fadd.2d`` at width 2, interleave 4, matching the
remark exactly — scanned as zero vector instructions.)
"""
from __future__ import annotations

import re

# AArch64: NEON vector registers (v0.2d, v1.16b, ...), SVE Z/P registers
# (z0.d, p7/z), quad registers used for 128-bit vector load/store/move (q0),
# and SVE-specific mnemonics (predicate generation, structured loads, etc).
AARCH64_VEC_RE = re.compile(
    r"\bv\d{1,2}\.\d*[bhsd]\b"                 # NEON vector reg w/ arrangement: v0.2d, v12.4s
    r"|\bz\d{1,2}\.[bhsd]\b"                   # SVE Z register: z0.d, z26.d
    r"|\bp\d{1,2}/[zm]\b"                      # SVE predicate governing a vector op: p7/z
    r"|\bq\d{1,2}\b"                           # 128-bit quad register (vector load/store/move)
    r"|\b(ld[1-4][bhwd]?|st[1-4][bhwd]?)\b"    # (SVE/NEON) structured / scalable load-store
    r"|\bwhilelo\b|\bwhilelt\b|\bwhilels\b|\bwhilehs\b|\bwhilege\b|\bwhilegt\b"
    r"|\bptrue\b|\bpfalse\b|\bmovprfx\b|\bfadda\b|\bfaddv\b|\blastb\b|\blasta\b"
    r"|\bcntb\b|\bcntd\b|\bcnth\b|\bcntw\b",
    re.IGNORECASE,
)

# x86: ymm/zmm registers are always vector (256/512-bit, never scalar). xmm
# is ambiguous on its own (scalar addsd/mulsd also use xmm), so it only
# counts when paired with a *packed* suffix (ps/pd) rather than scalar
# (ss/sd), or with an explicit FMA-packed mnemonic.
X86_VEC_RE = re.compile(
    r"%?[yz]mm\d{1,2}\b"
    r"|%?xmm\d{1,2}\b.*\b\w*p[sd]\d*\b"
    r"|\bvfmadd\d{3}p[sd]\b|\bvfmsub\d{3}p[sd]\b",
    re.IGNORECASE,
)

# Symbols that are runtime/support/stub code — never the actual kernel loop
# body — excluded from the scan so a stray vector instruction there can't
# produce a false "vectorized" verdict for the kernel itself.
NON_KERNEL_SYMBOL_RE = re.compile(
    r"dace_init|dace_exit|GLOBAL__sub_I|dacestub|_ZdlPv|_Znwm|"
    r"system_clock|chrono",
    re.IGNORECASE,
)

# Matches a function-start label in either objdump disassembly
# ("0000000000000000 <name>:") or raw compiler -S assembly ("name:", or
# Apple clang's "name:    ; comment" / GNU's "name:  # comment"). Local/
# internal labels (GNU ".L2:", ".LFB0:", Apple/LLVM "LBB0_4:" ...) are
# intentionally NOT matched (identifiers can't start with '.', and "LBB..."
# labels only fail to match here when they carry a comment — which is fine,
# they're basic blocks, not function entries) so they don't fragment a
# function into un-excluded pieces.
FUNC_LABEL_RE = re.compile(
    r"^[0-9a-f]{8,16}\s+<(?P<obj_name>[^>]+)>:\s*$"
    r"|^(?P<asm_name>[A-Za-z_$][\w$]*):(?:\s*(?:[;#]|//).*)?\s*$"
)


def split_into_functions(asm_text: str) -> list:
    """Split raw assembly/disassembly text into (symbol_name, body) chunks.

    Any text before the first matched label is kept under a synthetic
    "<preamble>" chunk instead of being dropped — a label regex that fails
    to match a real function entry (see module docstring) must not also
    silently delete that function's body.
    """
    chunks: list = []
    current_name = "<preamble>"
    current_lines: list = []

    for line in asm_text.splitlines():
        m = FUNC_LABEL_RE.match(line.strip())
        if m:
            chunks.append((current_name, "\n".join(current_lines)))
            current_name = m.group("obj_name") or m.group("asm_name")
            current_lines = []
        else:
            current_lines.append(line)

    chunks.append((current_name, "\n".join(current_lines)))
    return chunks


def parse_vec_from_asm(asm_text: str, *, kernel_functions_only: bool = True) -> dict:
    """
    Ground-truth vectorization check: scan actual assembly/machine code for
    SIMD register/instruction usage, rather than trusting compiler remarks.
    """
    functions = split_into_functions(asm_text)
    vec_lines: list = []

    for name, body in functions:
        if kernel_functions_only and NON_KERNEL_SYMBOL_RE.search(name):
            continue
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if AARCH64_VEC_RE.search(stripped) or X86_VEC_RE.search(stripped):
                vec_lines.append(stripped)

    return {
        "vectorized":     len(vec_lines) > 0,
        "vec_count":      len(vec_lines),
        "missed_count":   0,  # not derivable from assembly alone
        "sample_remarks": vec_lines[:5],
        "source":         "assembly",
    }
