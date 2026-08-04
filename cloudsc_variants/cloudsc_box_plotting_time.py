#!/usr/bin/env python3
"""
plot_variant_timings.py

Parses all bench_source.<compiler>_<cpu>_<cost_model>.txt result files produced
by bench_variants.py (found under timing_results_eiger/ and timing_results_daint/,
or any directories you point it at), and generates one grouped bar chart per
CloudSC variant (kernel). Each chart compares the 3 lanes (original Fortran,
DaCe fortran-frontend, DaCe python-frontend) across every combination of
CPU architecture (e.g. amd_epyc, arm_grace) and compiler (gcc, clang) found
in the data, for a given cost model.

Supported metrics (--metric):
    min_us, median_us, max_us, cold_us   -> raw timing in microseconds, log-scale
                                             bars with min/max error whiskers.
    ratio_vs_f                           -> speedup relative to original Fortran
                                             (Fortran_median / lane_median), linear
                                             scale, with a horizontal reference line
                                             at 1.0x (Fortran parity). Values above
                                             the line are faster than Fortran, below
                                             are slower. No error whiskers (ratio is
                                             a single derived value, not a range).

Expected input file naming (as produced by your sweep scripts):
    bench_source.<compiler>_<cpu...>_<cost_model>.txt
e.g. bench_source.gcc_amd_epyc_cheap.txt, bench_source.clang_arm_grace_default.txt

Expected table format inside each file (as printed by bench_variants.py):
    variant   lane   min_us  median_us  max_us  cold_us  ratio_vs_F  vs NumPy

Usage:
    python3 plot_variant_timings.py
    python3 plot_variant_timings.py --results-dirs timing_results_eiger timing_results_daint
    python3 plot_variant_timings.py --metric ratio_vs_f
    python3 plot_variant_timings.py --metric median_us --cost-models default
    python3 plot_variant_timings.py --out-dir plots --csv-out all_timings.csv
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ── Parsing ──────────────────────────────────────────────────────────────

FILENAME_RE = re.compile(r"^bench_source\.(?P<meta>.+)\.txt$")

ROW_RE = re.compile(
    r"^(?P<variant>\S+)\s+"
    r"(?P<lane>.+?)\s+"
    r"(?P<min_us>[\d.]+)\s+"
    r"(?P<median_us>[\d.]+)\s+"
    r"(?P<max_us>[\d.]+)\s+"
    r"(?P<cold_us>[\d.]+)\s+"
    r"(?P<ratio>-|[\d.]+x)\s+"
    r"(?P<status>PASS|FAIL)\s*$"
)

LANE_ORDER = ["original Fortran", "DaCe fortran-frontend", "DaCe python-frontend"]

RAW_TIMING_METRICS = {"min_us", "median_us", "max_us", "cold_us"}
RATIO_METRIC = "ratio_vs_f"


def parse_meta_from_filename(fname: str):
    """bench_source.<compiler>_<cpu...>_<cost_model>.txt -> (compiler, cpu, cost_model)."""
    m = FILENAME_RE.match(fname)
    if not m:
        return None
    tokens = m.group("meta").split("_")
    if len(tokens) < 3:
        return None
    compiler = tokens[0]
    cost_model = tokens[-1]
    cpu = "_".join(tokens[1:-1])
    return compiler, cpu, cost_model


def parse_result_file(path: pathlib.Path, cluster: str):
    meta = parse_meta_from_filename(path.name)
    if meta is None:
        print(f"  skip (unrecognized filename pattern): {path}", file=sys.stderr)
        return []
    compiler, cpu, cost_model = meta

    rows = []
    text = path.read_text(errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line or set(line) <= {"="} or set(line) <= {"-"}:
            continue
        if line.startswith("variant") and "lane" in line:
            continue
        m = ROW_RE.match(line)
        if not m:
            continue
        d = m.groupdict()
        raw_ratio = d["ratio"]
        if raw_ratio == "-":
            # This is the "original Fortran" baseline row itself: ratio to
            # itself is 1.0x by definition.
            ratio_val = 1.0
        else:
            ratio_val = float(raw_ratio.rstrip("x"))
        rows.append({
            "cluster": cluster,
            "compiler": compiler,
            "cpu": cpu,
            "cost_model": cost_model,
            "variant": d["variant"],
            "lane": d["lane"].strip(),
            "min_us": float(d["min_us"]),
            "median_us": float(d["median_us"]),
            "max_us": float(d["max_us"]),
            "cold_us": float(d["cold_us"]),
            "ratio_vs_f": ratio_val,
            "status": d["status"],
            "source_file": str(path),
        })
    return rows


def collect_all(results_dirs: list[pathlib.Path]) -> pd.DataFrame:
    all_rows = []
    for d in results_dirs:
        if not d.is_dir():
            print(f"WARNING: results dir not found, skipping: {d}", file=sys.stderr)
            continue
        cluster = d.name.replace("timing_results_", "") or d.name
        for f in sorted(d.glob("bench_source.*.txt")):
            rows = parse_result_file(f, cluster)
            all_rows.extend(rows)
            print(f"  parsed {len(rows):3d} rows from {f}")
    if not all_rows:
        print("No rows parsed from any file. Check --results-dirs.", file=sys.stderr)
        sys.exit(1)
    return pd.DataFrame(all_rows)


# ── Plotting ─────────────────────────────────────────────────────────────

def lane_sort_key(lane: str) -> int:
    try:
        return LANE_ORDER.index(lane)
    except ValueError:
        return len(LANE_ORDER)


def plot_variant(df: pd.DataFrame, variant: str, cost_model: str, metric: str,
                  out_dir: pathlib.Path, log_scale: bool):
    sub = df[(df["variant"] == variant) & (df["cost_model"] == cost_model)].copy()
    if sub.empty:
        return None

    lanes = sorted(sub["lane"].unique(), key=lane_sort_key)
    sub["combo"] = sub["cpu"] + " / " + sub["compiler"]
    combos = sorted(sub["combo"].unique())

    n_lanes = len(lanes)
    n_combos = len(combos)
    x = np.arange(n_lanes)
    width = 0.8 / max(n_combos, 1)

    is_ratio = (metric == RATIO_METRIC)

    fig, ax = plt.subplots(figsize=(max(7, 2.2 * n_lanes), 5.5))

    for i, combo in enumerate(combos):
        vals, err_lo, err_hi = [], [], []
        for lane in lanes:
            row = sub[(sub["combo"] == combo) & (sub["lane"] == lane)]
            if row.empty:
                vals.append(np.nan)
                err_lo.append(0)
                err_hi.append(0)
            else:
                r = row.iloc[0]
                vals.append(r[metric])
                if is_ratio:
                    err_lo.append(0)
                    err_hi.append(0)
                else:
                    err_lo.append(max(r[metric] - r["min_us"], 0))
                    err_hi.append(max(r["max_us"] - r[metric], 0))
        offset = (i - (n_combos - 1) / 2) * width
        kwargs = dict(width=width * 0.92, label=combo)
        if not is_ratio:
            kwargs.update(yerr=[err_lo, err_hi], capsize=3)
        ax.bar(x + offset, vals, **kwargs)

    ax.set_xticks(x)
    ax.set_xticklabels(lanes, rotation=15, ha="right")

    if is_ratio:
        ax.axhline(1.0, color="black", linewidth=1.2, linestyle="--",
                    label="Fortran parity (1.0x)")
        ax.set_ylabel("Speedup vs original Fortran (higher = faster)")
        ax.set_title(f"{variant} — ratio vs Fortran — cost model: {cost_model}")
        if log_scale:
            ax.set_yscale("log")
    else:
        ax.set_ylabel(f"{metric} (log scale)" if log_scale else metric)
        if log_scale:
            ax.set_yscale("log")
        ax.set_title(f"{variant}  —  cost model: {cost_model}")

    ax.legend(title="CPU arch / compiler", fontsize=9)
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    fig.tight_layout()

    suffix = "ratio_vs_fortran" if is_ratio else metric
    out_path = out_dir / f"timings_{variant}_{cost_model}_{suffix}.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


# ── Entry point ──────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--results-dirs", nargs="+",
                     default=["timing_results_eiger", "timing_results_daint"],
                     help="Directories containing bench_source.*.txt files.")
    ap.add_argument("--metric",
                     choices=["min_us", "median_us", "max_us", "cold_us", RATIO_METRIC],
                     default="median_us",
                     help="Which quantity to plot. 'ratio_vs_f' plots speedup "
                          "relative to original Fortran (Fortran_median / lane_median) "
                          "with a 1.0x parity reference line, instead of raw timings.")
    ap.add_argument("--cost-models", nargs="*", default=None,
                     help="Restrict to these cost models (default: all found).")
    ap.add_argument("--variants", nargs="*", default=None,
                     help="Restrict to these variants (default: all found).")
    ap.add_argument("--out-dir", default="plots")
    ap.add_argument("--csv-out", default="all_timings.csv")
    ap.add_argument("--no-log-scale", action="store_true",
                     help="Disable log-scale y-axis (linear instead). Applies to "
                          "both raw-timing and ratio_vs_f charts.")
    args = ap.parse_args()

    results_dirs = [pathlib.Path(p) for p in args.results_dirs]
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Collecting result files...")
    df = collect_all(results_dirs)
    df.to_csv(args.csv_out, index=False)
    print(f"\nWrote tidy CSV: {args.csv_out}  ({len(df)} rows)")

    variants = args.variants or sorted(df["variant"].unique())
    cost_models = args.cost_models or sorted(df["cost_model"].unique())

    print(f"\nVariants found:    {sorted(df['variant'].unique())}")
    print(f"CPUs found:        {sorted(df['cpu'].unique())}")
    print(f"Compilers found:   {sorted(df['compiler'].unique())}")
    print(f"Cost models found: {sorted(df['cost_model'].unique())}")

    n_fail = (df["status"] == "FAIL").sum()
    if n_fail:
        print(f"\nWARNING: {n_fail} rows have status=FAIL (diverged from NumPy oracle).")
        print(df[df["status"] == "FAIL"][["cluster", "compiler", "cpu", "cost_model",
                                           "variant", "lane"]].to_string(index=False))

    log_scale = not args.no_log_scale
    if args.metric == RATIO_METRIC and not args.no_log_scale:
        # Ratios cluster tightly around 1.0x; linear scale reads more naturally
        # by default, but log-scale is still available via omitting --no-log-scale
        # override is left to the user. Default to linear for ratio unless the
        # user explicitly wants log by re-running without --no-log-scale being
        # the deciding factor is kept simple: honor the same flag as timings.
        pass

    print("\nGenerating charts...")
    made = 0
    for variant in variants:
        for cm in cost_models:
            out_path = plot_variant(df, variant, cm, args.metric, out_dir,
                                     log_scale=log_scale)
            if out_path:
                print(f"  wrote {out_path}")
                made += 1

    print(f"\nDone. {made} chart(s) written to {out_dir}/")


if __name__ == "__main__":
    main()