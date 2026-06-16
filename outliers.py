"""
vectorization_diff.py

Compares vectorization results kernel-by-kernel across arbitrary
(compiler, cpu, cost_model, precision, tsvc_version, backend) combinations.

The key feature: each "side" of the comparison is independently configurable,
so you can compare e.g. clang/float/cpp vs gcc/double/dace, or
tsvc_2/double vs tsvc_2_5/double, or any other cross-cutting combination.

Expected directory layout (produced by run_sweep.py):
  <base_dir>/<tsvc_version>/[precision/]<compiler>_<cpu>_<cost_model>/vec_report.txt

Usage:
  # Default: all compilers x cpus x cost_models, tsvc_2 double, cpp vs dace
  python3 vectorization_diff.py

  # Compare clang float cpp vs gcc double dace
  python3 vectorization_diff.py \
    --left-compiler clang --left-precision float --left-backend cpp \
    --right-compiler gcc  --right-precision double --right-backend dace

  # Compare tsvc_2 vs tsvc_2_5 (same compiler/cost/backend, different version)
  python3 vectorization_diff.py \
    --left-tsvc-version tsvc_2   --left-backend cpp \
    --right-tsvc-version tsvc_2_5 --right-backend cpp

  # Sweep multiple compilers/cpus/cost-models (both sides use same set)
  python3 vectorization_diff.py \
    --compilers clang gcc --cpus apple_m_series intel_xeon \
    --cost-models default disabled

  # Fine-grained per-side control
  python3 vectorization_diff.py \
    --left-compilers clang --left-cost-models default cheap \
    --right-compilers gcc  --right-cost-models default cheap

Requirements:
  pip install (none beyond stdlib)
"""

import argparse
import csv
import pathlib
import re
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple


# ── Valid choices (mirrors run_sweep.py / vectorization_heatmap.py) ────────────
ALL_COMPILERS   = ["clang", "gcc", "icpx"]
ALL_COST_MODELS = ["default", "cheap", "unlimited", "disabled"]
ALL_CPUS        = [
    "amd_epyc", "amd_epyc_genoa", "apple_m_series",
    "arm_grace", "fugaku_a64fx", "ibm_power", "intel_xeon",
]
ALL_VERSIONS    = ["tsvc_2", "tsvc_2_5"]
ALL_PRECISIONS  = ["double", "float"]
ALL_BACKENDS    = ["cpp", "dace"]

DEFAULT_BASE_DIR = "."   # results_cpp / results_dace live here


# ── Directory resolution (matches run_sweep.py layout) ────────────────────────
def _results_root(
    base_dir: pathlib.Path,
    backend: str,
    tsvc_version: str,
    precision: str,
) -> pathlib.Path:
    """Return the folder containing <compiler>_<cpu>_<cost_model>/ subdirs.

    Probes the 'both' layout first (<base>/<version>/<precision>/) then the
    single-precision layout (<base>/<version>/).
    """
    subdir = "results_cpp" if backend == "cpp" else "results_dace"
    root = base_dir / subdir

    with_prec = root / tsvc_version / precision
    if with_prec.exists():
        return with_prec

    flat = root / tsvc_version
    if flat.exists():
        return flat

    return with_prec   # let caller emit a clear error


# ── Data loading ───────────────────────────────────────────────────────────────
@dataclass
class VecReport:
    vectorized:     Set[str] = field(default_factory=set)
    not_vectorized: Set[str] = field(default_factory=set)
    total:          int  = 0
    found:          bool = False
    has_detail:     bool = False


def parse_vec_report(path: pathlib.Path) -> VecReport:
    report = VecReport()
    if not path.exists():
        return report

    report.found = True
    text = path.read_text(errors="replace")

    for line in text.splitlines():
        stripped = line.strip()

        m = re.match(r"(?:DaCe\s+)?[Vv]ectorization\s+report:\s*(\d+)/(\d+)", stripped)
        if m:
            report.total = int(m.group(2))
            continue

        m = re.match(r"(VEC|---)\s+(\S+)", stripped)
        if m:
            kernel = m.group(2)
            if m.group(1) == "VEC":
                report.vectorized.add(kernel)
            else:
                report.not_vectorized.add(kernel)
            report.has_detail = True
            continue

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


def load_report(
    base_dir: pathlib.Path,
    backend: str,
    tsvc_version: str,
    precision: str,
    compiler: str,
    cpu: str,
    cost_model: str,
) -> Tuple[VecReport, pathlib.Path]:
    root = _results_root(base_dir, backend, tsvc_version, precision)
    path = root / f"{compiler}_{cpu}_{cost_model}" / "vec_report.txt"
    return parse_vec_report(path), path


# ── Side descriptor ────────────────────────────────────────────────────────────
@dataclass
class Side:
    label:        str
    backend:      str
    tsvc_version: str
    precision:    str
    compilers:    List[str]
    cpus:         List[str]
    cost_models:  List[str]
    base_dir:     pathlib.Path


def make_label(backend, tsvc_version, precision, compilers, cpus, cost_models) -> str:
    comp  = "/".join(compilers)  if len(compilers)  < 4 else "all"
    cpu_s = "/".join(cpus)       if len(cpus)       < 4 else "all"
    cm    = "/".join(cost_models) if len(cost_models) < 4 else "all"
    return f"{backend.upper()}·{tsvc_version}·{precision}·{comp}·{cpu_s}·{cm}"


# ── Diff logic ─────────────────────────────────────────────────────────────────
def compute_diff(left: VecReport, right: VecReport):
    if not left.has_detail or not right.has_detail:
        return None, None
    left_only  = left.vectorized  - right.vectorized
    right_only = right.vectorized - left.vectorized
    return left_only, right_only


# ── CLI ────────────────────────────────────────────────────────────────────────
def parse_args():
    ap = argparse.ArgumentParser(
        description="Diff vectorization results kernel-by-kernel across any two configurations.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
examples:
  # Default: all compilers x cpus x cost_models, tsvc_2 double, cpp vs dace
  python3 vectorization_diff.py

  # Compare clang float cpp vs gcc double dace
  python3 vectorization_diff.py \\
    --left-compiler clang --left-precision float  --left-backend cpp \\
    --right-compiler gcc  --right-precision double --right-backend dace

  # Compare tsvc_2 vs tsvc_2_5 (same backend, different version)
  python3 vectorization_diff.py \\
    --left-tsvc-version tsvc_2   --right-tsvc-version tsvc_2_5

  # Sweep multiple compilers/cpus, same cost-models on both sides
  python3 vectorization_diff.py \\
    --compilers clang gcc --cpus apple_m_series intel_xeon \\
    --cost-models default disabled

  # Fine-grained: different compiler sets per side
  python3 vectorization_diff.py \\
    --left-compilers clang --left-cost-models default cheap \\
    --right-compilers gcc  --right-cost-models default cheap

valid compilers   : {", ".join(ALL_COMPILERS)}
valid cost-models : {", ".join(ALL_COST_MODELS)}
valid cpus        : {", ".join(ALL_CPUS)}
valid versions    : {", ".join(ALL_VERSIONS)}
valid precisions  : {", ".join(ALL_PRECISIONS)}
valid backends    : {", ".join(ALL_BACKENDS)}
        """,
    )

    # ── Shared sweep parameters (apply to both sides unless overridden) ────────
    shared = ap.add_argument_group(
        "shared sweep parameters",
        "Applied to BOTH sides unless the corresponding --left-* / --right-* flag overrides it.",
    )
    shared.add_argument("--compilers",   nargs="+", default=["clang", "gcc"],  choices=ALL_COMPILERS,   metavar="C")
    shared.add_argument("--cpus",        nargs="+", default=["apple_m_series"], choices=ALL_CPUS,        metavar="CPU")
    shared.add_argument("--cost-models", nargs="+", default=ALL_COST_MODELS,   choices=ALL_COST_MODELS, metavar="CM")
    shared.add_argument("--base-dir",    default=".", metavar="DIR",
                        help="Root directory that contains results_cpp/ and results_dace/. (default: .)")

    # ── Left side ──────────────────────────────────────────────────────────────
    left = ap.add_argument_group("left side (defaults: cpp / tsvc_2 / double)")
    left.add_argument("--left-backend",      default="cpp",    choices=ALL_BACKENDS)
    left.add_argument("--left-tsvc-version", default="tsvc_2", choices=ALL_VERSIONS)
    left.add_argument("--left-precision",    default="double", choices=ALL_PRECISIONS)
    # single-value shortcuts
    left.add_argument("--left-compiler",    default=None, choices=ALL_COMPILERS,   metavar="C",
                      help="Pin left side to a single compiler (overrides --compilers for this side).")
    left.add_argument("--left-cpu",         default=None, choices=ALL_CPUS,        metavar="CPU",
                      help="Pin left side to a single CPU.")
    left.add_argument("--left-cost-model",  default=None, choices=ALL_COST_MODELS, metavar="CM",
                      help="Pin left side to a single cost model.")
    # multi-value overrides
    left.add_argument("--left-compilers",   nargs="+", default=None, choices=ALL_COMPILERS,   metavar="C")
    left.add_argument("--left-cpus",        nargs="+", default=None, choices=ALL_CPUS,        metavar="CPU")
    left.add_argument("--left-cost-models", nargs="+", default=None, choices=ALL_COST_MODELS, metavar="CM")

    # ── Right side ─────────────────────────────────────────────────────────────
    right = ap.add_argument_group("right side (defaults: dace / tsvc_2 / double)")
    right.add_argument("--right-backend",      default="dace",   choices=ALL_BACKENDS)
    right.add_argument("--right-tsvc-version", default="tsvc_2", choices=ALL_VERSIONS)
    right.add_argument("--right-precision",    default="double", choices=ALL_PRECISIONS)
    right.add_argument("--right-compiler",    default=None, choices=ALL_COMPILERS,   metavar="C")
    right.add_argument("--right-cpu",         default=None, choices=ALL_CPUS,        metavar="CPU")
    right.add_argument("--right-cost-model",  default=None, choices=ALL_COST_MODELS, metavar="CM")
    right.add_argument("--right-compilers",   nargs="+", default=None, choices=ALL_COMPILERS,   metavar="C")
    right.add_argument("--right-cpus",        nargs="+", default=None, choices=ALL_CPUS,        metavar="CPU")
    right.add_argument("--right-cost-models", nargs="+", default=None, choices=ALL_COST_MODELS, metavar="CM")

    # ── Output ─────────────────────────────────────────────────────────────────
    ap.add_argument("--out", default="vectorization_diff.csv", metavar="FILE",
                    help="Output CSV path (default: vectorization_diff.csv).")

    return ap.parse_args()


def _resolve_list(single, multi, shared):
    """Resolve a side's parameter: single-value > multi-value > shared."""
    if single is not None:
        return [single]
    if multi is not None:
        return multi
    return shared


def main():
    args = parse_args()
    base_dir = pathlib.Path(args.base_dir)

    left = Side(
        label        = "",
        backend      = args.left_backend,
        tsvc_version = args.left_tsvc_version,
        precision    = args.left_precision,
        compilers    = _resolve_list(args.left_compiler,   args.left_compilers,   args.compilers),
        cpus         = _resolve_list(args.left_cpu,        args.left_cpus,        args.cpus),
        cost_models  = _resolve_list(args.left_cost_model, args.left_cost_models, args.cost_models),
        base_dir     = base_dir,
    )
    left.label = make_label(left.backend, left.tsvc_version, left.precision,
                            left.compilers, left.cpus, left.cost_models)

    right = Side(
        label        = "",
        backend      = args.right_backend,
        tsvc_version = args.right_tsvc_version,
        precision    = args.right_precision,
        compilers    = _resolve_list(args.right_compiler,   args.right_compilers,   args.compilers),
        cpus         = _resolve_list(args.right_cpu,        args.right_cpus,        args.cpus),
        cost_models  = _resolve_list(args.right_cost_model, args.right_cost_models, args.cost_models),
        base_dir     = base_dir,
    )
    right.label = make_label(right.backend, right.tsvc_version, right.precision,
                             right.compilers, right.cpus, right.cost_models)

    print(f"LEFT  : {left.label}")
    print(f"RIGHT : {right.label}")

    rows            = []
    grand_left_only = 0
    grand_right_only= 0
    no_detail_count = 0

    # Cartesian product over the union of both sides' sweep axes
    for compiler in sorted(set(left.compilers) | set(right.compilers)):
        for cpu in sorted(set(left.cpus) | set(right.cpus)):
            for cm in sorted(set(left.cost_models) | set(right.cost_models),
                             key=ALL_COST_MODELS.index):

                tag = f"{compiler:6} | {cpu} | cost={cm}"

                # Only load if this combo is in scope for that side
                def _load(side: Side):
                    if compiler not in side.compilers or cpu not in side.cpus or cm not in side.cost_models:
                        return None, None
                    return load_report(side.base_dir, side.backend, side.tsvc_version,
                                       side.precision, compiler, cpu, cm)

                left_rpt,  left_path  = _load(left)
                right_rpt, right_path = _load(right)

                if left_rpt is None or right_rpt is None:
                    continue   # combo not applicable to one side

                if not left_rpt.found or not right_rpt.found:
                    missing = (["LEFT"]  if not left_rpt.found  else []) +  (["RIGHT"] if not right_rpt.found else [])
                    print(f"[{tag}]  SKIPPED — missing: {', '.join(missing)}")
                    continue

                left_only, right_only = compute_diff(left_rpt, right_rpt)

                if left_only is None:
                    print(f"[{tag}]  No per-kernel detail")
                    no_detail_count += 1
                    continue

                all_kernels = (left_rpt.vectorized | left_rpt.not_vectorized |
                               right_rpt.vectorized | right_rpt.not_vectorized)

                print(f"\n{'='*70}")
                print(f"[{tag}]")
                print(f"  Total kernels seen     : {len(all_kernels)}")
                print(f"  LEFT  ({left.backend}/{left.precision}) vectorized  : {len(left_rpt.vectorized):>4}")
                print(f"  RIGHT ({right.backend}/{right.precision}) vectorized : {len(right_rpt.vectorized):>4}")
                print(f"  LEFT-only  (+L, -R)   : {len(left_only):>4}")
                print(f"  RIGHT-only (-L, +R)   : {len(right_only):>4}")
                print(f"  Both vectorized        : {len(left_rpt.vectorized & right_rpt.vectorized):>4}")
                print(f"  Neither vectorized     : {len(all_kernels - left_rpt.vectorized - right_rpt.vectorized):>4}")

                for kernels, direction, label in [
                    (left_only,  "left_only",  f"LEFT only  (+{left.backend}/{left.precision}, -{right.backend}/{right.precision})"),
                    (right_only, "right_only", f"RIGHT only (-{left.backend}/{left.precision}, +{right.backend}/{right.precision})"),
                ]:
                    if kernels:
                        print(f"\n  ++ {label} ({len(kernels)}) ++")
                        for k in sorted(kernels):
                            print(f"      {k}")
                            rows.append({
                                "compiler":        compiler,
                                "cpu":             cpu,
                                "cost_model":      cm,
                                "kernel":          k,
                                "direction":       direction,
                                "left_backend":    left.backend,
                                "left_version":    left.tsvc_version,
                                "left_precision":  left.precision,
                                "right_backend":   right.backend,
                                "right_version":   right.tsvc_version,
                                "right_precision": right.precision,
                            })

                grand_left_only  += len(left_only)
                grand_right_only += len(right_only)

    # ── CSV ────────────────────────────────────────────────────────────────────
    out_path = pathlib.Path(args.out)
    if rows:
        with out_path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nSaved {len(rows)} differing kernels -> {out_path.resolve()}")
    else:
        print("\nNo differing kernels found.")

    # ── Grand summary ──────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("GRAND TOTALS")
    print(f"  LEFT-only  : {grand_left_only}  ({left.label})")
    print(f"  RIGHT-only : {grand_right_only}  ({right.label})")
    if no_detail_count:
        print(f"  Skipped (no per-kernel detail) : {no_detail_count}")
    print()


if __name__ == "__main__":
    main()