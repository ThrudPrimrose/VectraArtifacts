#!/usr/bin/env python3
"""Aggregate vectorization reports from multiple independent cluster runs.

Scans existing vec_reports/<kernel>/<cell>/ artifact folders (produced by
prior runs of only_vec_cloudsc_sdfg.py with different --compilers/--cpus)
and rebuilds a single combined vectorization_report_<kernel>.txt per
benchmark, without recompiling anything.


python3 merge_vectorization_reports.py \
  --root cloudsc_variants \
  --compilers clang gcc \
  --cost-models default cheap unlimited disabled \
  --cpus amd_epyc arm_grace
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
from typing import Iterable

_LOC_RE = re.compile(r"^([^:]+):(\d+):(\d+)")

VEC_HIT_RE = re.compile(r"(remark:\s*(vectorized loop|interleaved loop)|optimized: loop vectorized using)", re.IGNORECASE)
VEC_MISS_RE = re.compile(r"(remark:\s*loop not vectorized(?!:)|missed: couldn't vectorize loop)", re.IGNORECASE)
WHY_RE = re.compile(
    r"(remark:\s*loop not vectorized:|missed: not vectorized:|optimized:\s*loop versioned|"
    r"remark:\s*the cost-model indicates|Unsafe indirect dependence|"
    r"cannot vectorize outer loop|outer loop cannot|has inner loop)",
    re.IGNORECASE,
)


def _count_unique_locations(lines: list[str], kernel_cpp: str | None = None) -> int:
    locs: set[str] = set()
    for s in lines:
        m = _LOC_RE.match(s)
        if not m:
            continue
        filepath = m.group(1)
        if kernel_cpp and not filepath.endswith(kernel_cpp):
            continue
        locs.add(m.group())
    return len(locs)


def summarize_vectorization(text: str, kernel_cpp: str | None = None) -> tuple[str, list[str], int, int]:
    hits, misses, why = [], [], []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        if VEC_HIT_RE.search(s):
            hits.append(s)
        elif VEC_MISS_RE.search(s):
            misses.append(s)
        if WHY_RE.search(s):
            why.append(s)
        elif i + 1 < len(lines) and WHY_RE.search(lines[i + 1].strip()):
            why.append(lines[i + 1].strip())
    vec_count = _count_unique_locations(hits, kernel_cpp)
    miss_count = _count_unique_locations(misses, kernel_cpp)
    if hits:
        return "yes", (hits + misses + why)[:12], vec_count, miss_count
    if misses:
        return "no", (misses + why)[:12], vec_count, miss_count
    return "unknown", ([*why][:12] or ["No explicit vectorization remark found."]), 0, 0


def _read_rc(out_dir: pathlib.Path) -> int:
    """Best-effort: infer return code from presence of stderr content /
    build folder; falls back to 0 if unknown."""
    stderr_path = out_dir / "stderr.txt"
    if stderr_path.exists() and "CompilerConfigurationError" in stderr_path.read_text(errors="replace"):
        return 1
    return 0


def build_cell_report_lines(cell: str, out_dir: pathlib.Path, kernel_cpp: str) -> list[str]:
    rpt_path = out_dir / "vec_remarks.rpt"
    summary_path = out_dir / "summary.txt"
    if rpt_path.exists():
        count_text = rpt_path.read_text(errors="replace")
    elif summary_path.exists():
        count_text = summary_path.read_text(errors="replace")
    else:
        return [
            "",
            f"=== {cell} ===",
            "SKIP — no artifacts found (this compiler/cpu/cost-model was not run).",
        ]

    status, reasons, vec_count, miss_count = summarize_vectorization(count_text, kernel_cpp)
    total = vec_count + miss_count
    count_str = f"{vec_count}/{total} loops vectorized" if total > 0 else "no loop counts available"
    rc = _read_rc(out_dir)
    return [
        "",
        f"=== {cell} ===",
        f"Return code: {rc}",
        f"Vectorized: {status}",
        f"Loop counts: {count_str} ({miss_count} not vectorized)",
        "Reasons:",
        *[f"- {r}" for r in reasons],
        f"Artifacts: {out_dir.as_posix()}/",
    ]


def build_fortran_report_lines(cell: str, fort_out: pathlib.Path) -> list[str]:
    rpt_path = fort_out / "vec_remarks.rpt"
    if not rpt_path.exists():
        return [
            "",
            f"--- Fortran baseline [{cell}] ---",
            "SKIP — no Fortran artifacts found for this cell.",
        ]
    text = rpt_path.read_text(errors="replace")
    status, reasons, vec_count, miss_count = summarize_vectorization(text)
    total = vec_count + miss_count
    fcount = f"{vec_count}/{total} loops vectorized" if total > 0 else "no loop counts available"
    return [
        "",
        f"--- Fortran baseline [{cell}] ---",
        f"Vectorized: {status}",
        f"Loop counts: {fcount} ({miss_count} not vectorized)",
        "Reasons:",
        *[f"- {r}" for r in reasons],
        f"Artifacts: {fort_out.as_posix()}/",
    ]


def discover_sdfg_dirs(root: pathlib.Path) -> list[tuple[str, pathlib.Path, str]]:
    """Find benchmark dirs that have a vec_reports/<kernel_stem>/ folder."""
    found = []
    for vec_reports_dir in sorted(root.rglob("vec_reports")):
        bench_dir = vec_reports_dir.parent
        bench_name = bench_dir.name
        for kernel_dir in sorted(vec_reports_dir.iterdir()):
            if not kernel_dir.is_dir() or kernel_dir.name == "fortran":
                continue
            found.append((bench_name, bench_dir, kernel_dir.name))
    return found


def parse_args(argv: Iterable[str] | None = None):
    ap = argparse.ArgumentParser(description="Merge vectorization reports from multiple prior runs.")
    ap.add_argument("--root", default="cloudsc_variants")
    ap.add_argument("--compilers", nargs="+", default=["clang", "gcc"])
    ap.add_argument("--cost-models", nargs="+", default=["default", "cheap", "unlimited", "disabled"])
    ap.add_argument("--cpus", nargs="+", default=["amd_epyc", "arm_grace"])
    return ap.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    root = pathlib.Path(args.root)
    if not root.exists():
        print(f"Root folder not found: {root}", file=sys.stderr)
        return 2

    entries = discover_sdfg_dirs(root)
    if not entries:
        print(f"No vec_reports found under {root}", file=sys.stderr)
        return 1

    seen: dict[tuple[str, str], list[str]] = {}
    for bench_name, bench_dir, kernel_stem in entries:
        seen.setdefault((bench_name, kernel_stem), []).append(str(bench_dir))

    for (bench_name, kernel_stem), bench_dirs in seen.items():
        bench_dir = pathlib.Path(bench_dirs[0])
        kernel_cpp = f"{kernel_stem}.cpp"
        report_lines = [f"Benchmark: {bench_name}", f"SDFG: {kernel_stem}.sdfg"]

        for compiler in args.compilers:
            for cost_model in args.cost_models:
                if compiler == "clang" and cost_model == "cheap":
                    continue
                for cpu in args.cpus:
                    cell = f"{compiler}_{cpu}_{cost_model}"
                    out_dir = bench_dir / "vec_reports" / kernel_stem / cell
                    report_lines.extend(build_cell_report_lines(cell, out_dir, kernel_cpp))

                    fort_out = bench_dir / "vec_reports" / "fortran" / bench_name / cell
                    report_lines.extend(build_fortran_report_lines(cell, fort_out))

        report_path = bench_dir / f"vectorization_report_{kernel_stem}.txt"
        report_path.write_text("\n".join(report_lines) + "\n")
        print(f"Saved merged report: {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())