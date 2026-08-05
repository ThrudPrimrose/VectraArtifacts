#!/usr/bin/env python3
"""Plot CloudSC timing results.

This script parses bench_source.*.txt files produced by bench_variants.py and
creates timing comparison charts.

Default mode:
    - one figure per kernel (variant)
    - one figure per cost model
    - x-axis: lanes
    - grouped bars: compiler / cpu combinations

New flag:
    --combine-cost-models
    When set, the script produces one larger figure per kernel that combines
    *all* cost models into a single graph instead of making separate graphs per
    cost model.

Example:
    python3 cloudsc_box_plotting_time.py --results-dirs timing_results_eiger timing_results_daint
    python3 cloudsc_box_plotting_time.py --combine-cost-models

Expected result file format:
    bench_source.<compiler>_<cpu...>_<cost_model>.txt
and rows like:
    variant  lane  min_us  median_us  max_us  cold_us  ratio_vs_F  vs NumPy
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

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


def parse_meta(fname: str):
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


def parse_file(path: pathlib.Path, cluster: str):
    meta = parse_meta(path.name)
    if meta is None:
        return []
    compiler, cpu, cost_model = meta
    rows = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("=") or line.startswith("-") or line.startswith("variant"):
            continue
        m = ROW_RE.match(line)
        if not m:
            continue
        d = m.groupdict()
        ratio = 1.0 if d["ratio"] == "-" else float(d["ratio"].rstrip("x"))
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
            "ratio_vs_f": ratio,
            "status": d["status"],
            "source_file": str(path),
        })
    return rows


def collect_df(results_dirs):
    rows = []
    for d in results_dirs:
        d = pathlib.Path(d)
        if not d.is_dir():
            print(f"WARNING: missing results dir {d}", file=sys.stderr)
            continue
        cluster = d.name.replace("timing_results_", "")
        for f in sorted(d.glob("bench_source.*.txt")):
            rows.extend(parse_file(f, cluster))
    if not rows:
        raise SystemExit("No timing rows parsed.")
    return pd.DataFrame(rows)


def lane_key(lane):
    return LANE_ORDER.index(lane) if lane in LANE_ORDER else len(LANE_ORDER)


def plot_variant_one_cost_model(df, variant, cost_model, metric, out_dir, log_scale):
    sub = df[(df.variant == variant) & (df.cost_model == cost_model)].copy()
    if sub.empty:
        return None
    return _plot_grouped(sub, variant, cost_model, metric, out_dir, log_scale)


def plot_variant_combined(df, variant, metric, out_dir, log_scale):
    sub = df[df.variant == variant].copy()
    if sub.empty:
        return None
    return _plot_grouped(sub, variant, "all_cost_models", metric, out_dir, log_scale, combined=True)


def _plot_grouped(sub, variant, cost_model, metric, out_dir, log_scale, combined=False):
    lanes = sorted(sub["lane"].unique(), key=lane_key)
    sub["combo"] = sub["cluster"] + " / " + sub["cpu"] + " / " + sub["compiler"]
    combos = sorted(sub["combo"].unique())

    x = np.arange(len(lanes))
    width = 0.8 / max(len(combos), 1)
    is_ratio = metric == "ratio_vs_f"

    fig, ax = plt.subplots(figsize=(max(10, 2.5 * len(lanes)), 6))
    for i, combo in enumerate(combos):
        vals, lo, hi = [], [], []
        for lane in lanes:
            row = sub[(sub.combo == combo) & (sub.lane == lane)]
            if row.empty:
                vals.append(np.nan)
                lo.append(0)
                hi.append(0)
                continue
            r = row.iloc[0]
            vals.append(r[metric])
            if is_ratio:
                lo.append(0)
                hi.append(0)
            else:
                lo.append(max(r[metric] - r["min_us"], 0))
                hi.append(max(r["max_us"] - r[metric], 0))
        off = (i - (len(combos) - 1) / 2) * width
        kwargs = dict(width=width * 0.92, label=combo)
        if not is_ratio:
            kwargs.update(yerr=[lo, hi], capsize=3)
        ax.bar(x + off, vals, **kwargs)

    ax.set_xticks(x)
    ax.set_xticklabels(lanes, rotation=15, ha="right")

    if is_ratio:
        ax.axhline(1.0, color="black", linestyle="--", linewidth=1)
        ax.set_ylabel("Speedup vs original Fortran")
    else:
        ax.set_ylabel(metric)
        if log_scale:
            ax.set_yscale("log")

    title = f"{variant}"
    if combined:
        title += " — all cost models"
    else:
        title += f" — {cost_model}"
    ax.set_title(title)
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    ax.legend(title="cluster / cpu / compiler", fontsize=8)
    fig.tight_layout()

    suffix = "combined" if combined else cost_model
    out_path = out_dir / f"timings_{variant}_{suffix}_{metric}.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dirs", nargs="+", default=["timing_results_eiger", "timing_results_daint"])
    ap.add_argument("--metric", choices=["min_us", "median_us", "max_us", "cold_us", "ratio_vs_f"], default="median_us")
    ap.add_argument("--cost-models", nargs="*", default=None)
    ap.add_argument("--variants", nargs="*", default=None)
    ap.add_argument("--out-dir", default="plots")
    ap.add_argument("--csv-out", default="all_timings.csv")
    ap.add_argument("--no-log-scale", action="store_true")
    ap.add_argument("--combine-cost-models", action="store_true",
                    help="For each kernel, combine all cost models into one large figure.")
    args = ap.parse_args()

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df = collect_df(args.results_dirs)
    df.to_csv(args.csv_out, index=False)

    variants = args.variants or sorted(df.variant.unique())
    if args.cost_models is not None and not args.combine_cost_models:
        cost_models = args.cost_models
    else:
        cost_models = sorted(df.cost_model.unique())

    made = 0
    if args.combine_cost_models:
        for variant in variants:
            p = plot_variant_combined(df, variant, args.metric, out_dir, not args.no_log_scale)
            if p:
                print(f"wrote {p}")
                made += 1
    else:
        for variant in variants:
            for cm in cost_models:
                p = plot_variant_one_cost_model(df, variant, cm, args.metric, out_dir, not args.no_log_scale)
                if p:
                    print(f"wrote {p}")
                    made += 1

    print(f"done: {made} figure(s)")


if __name__ == "__main__":
    main()