"""Patch DaCe 0.16.x state_parent_tree — fix ALL idom KeyError sites.

There are two unguarded idom lookups in state_parent_tree:
  1. Line ~173:  curdom = idom[state]          — initial lookup
  2. Line ~181:  while curdom != idom[curdom]  — loop condition

Both raise KeyError for unreachable states absent from the idom dict.
This patch rewrites the entire inner loop block to guard both sites.
Safe to run repeatedly.
"""
import pathlib
import sys

p = pathlib.Path(
    "/usr/local/lib/python3.11/site-packages/dace/sdfg/analysis/cfg.py"
)
if not p.exists():
    print("DaCe cfg.py not found — skipping patch")
    sys.exit(0)

src = p.read_text()

SENTINEL = "# [vectra-patch] state_parent_tree idom guard applied"
if SENTINEL in src:
    print("DaCe state_parent_tree already patched — nothing to do")
    sys.exit(0)

# ── Patch 1: guard the initial lookup ─────────────────────────────────────────
old1 = "        curdom = idom[state]\n"
new1 = (
    "        if state not in idom:  # [vectra-patch] state_parent_tree idom guard applied\n"
    "            parents[state] = None\n"
    "            continue\n"
    "        curdom = idom[state]\n"
)

# ── Patch 2: guard the while-loop condition ────────────────────────────────────
# Two known variants depending on exact DaCe sub-version:
old2a = "        while curdom != idom[curdom]:\n"
new2a = "        while curdom in idom and curdom != idom[curdom]:\n"

old2b = (
    "        while curdom != idom[curdom]:\n"
    "            if sdfg.out_degree(curdom) > 1:\n"
    "                break\n"
    "            curdom = idom[curdom]\n"
)
new2b = (
    "        while curdom in idom and curdom != idom[curdom]:\n"
    "            if sdfg.out_degree(curdom) > 1:\n"
    "                break\n"
    "            curdom = idom[curdom]\n"
)

patched = src

# Apply patch 1
if old1 in patched:
    patched = patched.replace(old1, new1, 1)
    print("  ✓ Patch 1 applied: guarded idom[state] initial lookup")
else:
    print("  ! Patch 1 skipped: idom[state] pattern not found (may already be safe)")

# Apply patch 2 — try longer variant first, fall back to simple variant
if old2b in patched:
    patched = patched.replace(old2b, new2b, 1)
    print("  ✓ Patch 2 applied: guarded while-loop condition (with out_degree variant)")
elif old2a in patched:
    patched = patched.replace(old2a, new2a, 1)
    print("  ✓ Patch 2 applied: guarded while-loop condition (simple variant)")
else:
    print("  ! Patch 2 skipped: while-loop pattern not found (may already be safe)")

if patched == src:
    idx = src.find("idom")
    snippet = src[max(0, idx - 100): idx + 400] if idx != -1 else "<not found>"
    print(f"ERROR: no patterns matched in {p}\nContext around 'idom':\n{snippet}", file=sys.stderr)
    sys.exit(1)

p.write_text(patched)
print(f"Applied DaCe state_parent_tree bugfix to {p}")