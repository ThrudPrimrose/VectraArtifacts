"""
vectorization_diff.py

Compares C++ vs DaCe vectorization results kernel-by-kernel for each
(compiler, cpu_arch, cost_model) combination.

For every permutation it finds kernels where:
  - CPP vectorized but DaCe did NOT  (cpp_only)
  - DaCe vectorized but CPP did NOT  (dace_only)

Output:
  - Printed summary to stdout
  - A CSV file (vectorization_diff.csv) with one row per differing kernel

Expected directory layout:
  results_cpp/<compiler>_<cpu>_<cost_model>/vec_report.txt
  results_dace/<compiler>_<cpu>_<cost_model>/vec_report.txt

vec_report.txt format:
  DaCe vectorization report: 72/151 kernels vectorized
    VEC  s000_d_single
    ---  s111_d_single
    ...

  (CPP reports use the same VEC/--- format)

Usage:
  python3 vectorization_diff.py
  python3 vectorization_diff.py --cpp-dir results_cpp --dace-dir results_dace --out diff.csv
"""

import argparse
import csv
import pathlib
import re
import sys
from dataclasses import dataclass, field
from typing import Optional, Set


# ── Configuration ──────────────────────────────────────────────────────────────
COMPILERS   = ["clang", "gcc"]
CPU_ARCHS   = ["apple_m_series"]
# CPU_ARCHS = [
#     "apple_m_series", "arm_grace", "amd_epyc", "amd_epyc_genoa",
#     "intel_xeon", "ibm_power", "fugaku_a64fx",
# ]
COST_MODELS = ["default", "cheap", "unlimited", "disabled"]


# ── Data loading ───────────────────────────────────────────────────────────────
@dataclass
class VecReport:
    vectorized:     Set[str] = field(default_factory=set)
    not_vectorized: Set[str] = field(default_factory=set)
    total:          int  = 0
    found:          bool = False
    has_detail:     bool = False   # True if per-kernel lines were parsed


def parse_vec_report(path: pathlib.Path) -> VecReport:
    """
    Parse a vec_report.txt file.

    Supported per-kernel line formats:
      VEC  <kernel>          (vectorized)
      ---  <kernel>          (not vectorized)
      VECTORIZED: <kernel>   (legacy explicit form)
      NOT VECTORIZED: <kernel>
    """
    report = VecReport()
    if not path.exists():
        return report

    report.found = True
    text = path.read_text(errors="replace")

    for line in text.splitlines():
        stripped = line.strip()

        # Summary line (either prefix works)
        m = re.match(r"(?:DaCe\s+)?[Vv]ectorization\s+report:\s*(\d+)/(\d+)", stripped)
        if m:
            report.total = int(m.group(2))
            continue

        # VEC / --- format  (primary format)
        m = re.match(r"(VEC|---)\s+(\S+)", stripped)
        if m:
            kernel = m.group(2)
            if m.group(1) == "VEC":
                report.vectorized.add(kernel)
            else:
                report.not_vectorized.add(kernel)
            report.has_detail = True
            continue

        # Legacy explicit format (fallback)
        m = re.match(r"VECTORIZED:\s*(\S+)", stripped, re.IGNORECASE)
        if m:
            report.vectorized.add(m.group(1))
            report.has_detail = True
            continue

        m = re.match(r"NOT\s+VECTORIZED:\s*(\S+)", stripped, re.IGNORECASE)
        if m:
            report.not_vectorized.add(m.group(1))
            report.has_detail = True

    return report


# ── Diff logic ─────────────────────────────────────────────────────────────────
def compute_diff(cpp: VecReport, dace: VecReport):
    """
    Return (cpp_only, dace_only) sets.
    Returns (None, None) if either report lacks per-kernel detail.
    """
    if not cpp.has_detail or not dace.has_detail:
        return None, None
    cpp_only  = cpp.vectorized  - dace.vectorized
    dace_only = dace.vectorized - cpp.vectorized
    return cpp_only, dace_only


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="Diff CPP vs DaCe vectorization results kernel-by-kernel."
    )
    ap.add_argument("--cpp-dir",  default="results_cpp",  metavar="DIR")
    ap.add_argument("--dace-dir", default="results_dace", metavar="DIR")
    ap.add_argument("--out",      default="vectorization_diff.csv", metavar="FILE")
    args = ap.parse_args()

    cpp_root  = pathlib.Path(args.cpp_dir)
    dace_root = pathlib.Path(args.dace_dir)

    for d, flag in [(cpp_root, "--cpp-dir"), (dace_root, "--dace-dir")]:
        if not d.exists():
            sys.exit(f"ERROR: directory not found: {d!r} ({flag})")

    rows            = []
    grand_cpp_only  = 0
    grand_dace_only = 0
    no_detail_count = 0

    for compiler in COMPILERS:
        for cpu in CPU_ARCHS:
            for cm in COST_MODELS:
                name = f"{compiler}_{cpu}_{cm}"
                tag  = f"{compiler:6} | {cpu} | cost={cm}"

                cpp_rpt  = parse_vec_report(cpp_root  / name / "vec_report.txt")
                dace_rpt = parse_vec_report(dace_root / name / "vec_report.txt")

                # Missing report files
                if not cpp_rpt.found or not dace_rpt.found:
                    missing = (["CPP"]  if not cpp_rpt.found  else []) +                               (["DaCe"] if not dace_rpt.found else [])
                    print(f"[{tag}]  SKIPPED — missing report: {', '.join(missing)}")
                    continue

                cpp_only, dace_only = compute_diff(cpp_rpt, dace_rpt)

                if cpp_only is None:
                    print(f"[{tag}]  No per-kernel detail "
                          f"(CPP {len(cpp_rpt.vectorized)} vec / "
                          f"DaCe {len(dace_rpt.vectorized)} vec)")
                    no_detail_count += 1
                    continue

                # All kernels seen by either side
                all_kernels = (cpp_rpt.vectorized | cpp_rpt.not_vectorized |
                               dace_rpt.vectorized | dace_rpt.not_vectorized)

                print(f"\n{'='*65}")
                print(f"[{tag}]")
                print(f"  Total kernels seen : {len(all_kernels)}")
                print(f"  CPP  vectorized    : {len(cpp_rpt.vectorized):>4}")
                print(f"  DaCe vectorized    : {len(dace_rpt.vectorized):>4}")
                print(f"  CPP-only  (+CPP, -DaCe) : {len(cpp_only):>4}")
                print(f"  DaCe-only (-CPP, +DaCe) : {len(dace_only):>4}")
                print(f"  Both vectorized         : "
                      f"{len(cpp_rpt.vectorized & dace_rpt.vectorized):>4}")
                print(f"  Neither vectorized      : "
                      f"{len(all_kernels - cpp_rpt.vectorized - dace_rpt.vectorized):>4}")

                if cpp_only:
                    print(f"\n  ++ CPP vectorized, DaCe did NOT ({len(cpp_only)}) ++")
                    for k in sorted(cpp_only):
                        print(f"      {k}")
                        rows.append({"compiler": compiler, "cpu": cpu,
                                     "cost_model": cm, "kernel": k,
                                     "direction": "cpp_only"})

                if dace_only:
                    print(f"\n  ++ DaCe vectorized, CPP did NOT ({len(dace_only)}) ++")
                    for k in sorted(dace_only):
                        print(f"      {k}")
                        rows.append({"compiler": compiler, "cpu": cpu,
                                     "cost_model": cm, "kernel": k,
                                     "direction": "dace_only"})

                grand_cpp_only  += len(cpp_only)
                grand_dace_only += len(dace_only)

    # ── CSV output ─────────────────────────────────────────────────────────────
    out_path = pathlib.Path(args.out)
    if rows:
        with out_path.open("w", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=["compiler", "cpu", "cost_model", "kernel", "direction"]
            )
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nSaved {len(rows)} differing kernels -> {out_path.resolve()}")
    else:
        print("\nNo differing kernels found.")

    # ── Grand summary ──────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("GRAND TOTALS (all permutations)")
    print(f"  CPP-only  (+CPP, -DaCe) : {grand_cpp_only}")
    print(f"  DaCe-only (-CPP, +DaCe) : {grand_dace_only}")
    if no_detail_count:
        print(f"  Skipped (no detail)     : {no_detail_count}")
    print()


if __name__ == "__main__":
    main()