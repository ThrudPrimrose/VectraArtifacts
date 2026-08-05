#!/usr/bin/env python3
"""Plot CloudSC timing results, including box plots from raw repetition data.

Inputs:
  1) summary files: bench_source.<compiler>_<cpu...>_<cost_model>.txt
  2) raw files:     raw_data_<variant>_<compiler>.txt

In boxplot mode, the script makes one figure per variant with all available:
  - cost models
  - CPUs (inferred from folder name timing_results_<cpu>)
  - compilers
  - lanes
on a single graph.

That yields roughly 24 separate box plots per kernel when everything is present.

Usage examples:
  python3 cloudsc_box_plotting_time.py --boxplot
  python3 cloudsc_box_plotting_time.py --boxplot --results-dirs timing_results_eiger timing_results_daint

The legend now distinguishes CPU/compiler/cost-model combinations, and each box
has its own color.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from itertools import cycle

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SUMMARY_FILE_RE = re.compile(r"^bench_source\.(?P<meta>.+)\.txt$")
RAW_FILE_RE = re.compile(r"^raw_data_(?P<variant>.+)_(?P<compiler>[^_]+)\.txt$")
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


def cpu_from_dir(d: pathlib.Path) -> str:
    name = d.name
    if name.startswith("timing_results_"):
        return name.replace("timing_results_", "")
    return name


def parse_summary_meta(fname: str):
    m = SUMMARY_FILE_RE.match(fname)
    if not m:
        return None
    tokens = m.group("meta").split("_")
    if len(tokens) < 3:
        return None
    compiler = tokens[0]
    cost_model = tokens[-1]
    cpu = "_".join(tokens[1:-1])
    return compiler, cpu, cost_model


def parse_summary_file(path: pathlib.Path, cluster: str):
    meta = parse_summary_meta(path.name)
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
            "source": "summary",
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


def parse_raw_file(path: pathlib.Path, cluster: str):
    m = RAW_FILE_RE.match(path.name)
    if not m:
        return []
    variant = m.group("variant")
    compiler = m.group("compiler")
    cpu = cpu_from_dir(path.parent)
    rows = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("variant"):
            continue
        cols = re.split(r"\s+", line)
        if len(cols) < 4:
            continue
        try:
            us = float(cols[-1])
            rep = int(cols[-2])
            lane = " ".join(cols[1:-2])
            row_variant = cols[0]
        except ValueError:
            continue
        rows.append({
            "source": "raw",
            "cluster": cluster,
            "compiler": compiler,
            "cpu": cpu,
            "variant": row_variant,
            "lane": lane,
            "rep": rep,
            "us": us,
            "source_file": str(path),
        })
    return rows


def collect_data(results_dirs):
    summary_rows = []
    raw_rows = []
    for d in results_dirs:
        d = pathlib.Path(d)
        if not d.is_dir():
            print(f"WARNING: missing results dir {d}", file=sys.stderr)
            continue
        cluster = cpu_from_dir(d)
        for f in sorted(d.glob("bench_source.*.txt")):
            summary_rows.extend(parse_summary_file(f, cluster))
        for f in sorted(d.glob("raw_data_*.txt")):
            raw_rows.extend(parse_raw_file(f, cluster))
    return pd.DataFrame(summary_rows), pd.DataFrame(raw_rows)


def lane_key(lane):
    return LANE_ORDER.index(lane) if lane in LANE_ORDER else len(LANE_ORDER)


def plot_boxplots(raw_df, variant, out_dir):
    sub = raw_df[raw_df["variant"] == variant].copy()
    if sub.empty:
        return None

    lanes = sorted(sub["lane"].unique(), key=lane_key)
    combos = sorted(sub[["cpu", "compiler"]].drop_duplicates().itertuples(index=False, name=None))
    cost_models = sorted(sub["cost_model"].dropna().unique())

    # If cost_model is not encoded in raw files, infer it from the source summary files not possible.
    # In raw mode we still keep a 24-box layout by using all unique cluster/cpu/compiler/lane groups.
    # If multiple cost-models are truly present, they must be encoded in the raw file or sidecar path.
    # Here we map each raw file to a pseudo cost-model from the file name if available.
    if "cost_model" not in sub.columns:
        sub["cost_model"] = "unknown"
        cost_models = ["unknown"]

    # Fall back to a per-file pseudo cost-model label if the raw files were generated per run.
    # This keeps every box distinct on one graph.
    if (sub["cost_model"] == "unknown").all():
        sub["cost_model"] = sub["source_file"].apply(lambda p: pathlib.Path(p).stem)
        cost_models = sorted(sub["cost_model"].unique())

    # Build one box per (cpu, compiler, cost_model, lane).
    groups = []
    for cost in cost_models:
        for cpu, compiler in combos:
            for lane in lanes:
                vals = sub[(sub["cost_model"] == cost) & (sub["cpu"] == cpu) & (sub["compiler"] == compiler) & (sub["lane"] == lane)]["us"].tolist()
                if vals:
                    groups.append((cost, cpu, compiler, lane, vals))

    if not groups:
        return None

    # Arrange groups along x: lanes are the main axis; within each lane, every cost/cpu/compiler box is shown.
    fig, ax = plt.subplots(figsize=(max(18, 3.6 * len(lanes)), 8))
    lane_span = 1.0
    n_per_lane = len([g for g in groups if g[3] == lanes[0]]) if lanes else len(groups)
    per_lane_count = max(len(groups) // max(len(lanes), 1), 1)
    box_width = 0.8 / max(per_lane_count, 1)

    positions = []
    data = []
    colors = []
    labels = []
    palette = cycle(plt.cm.tab20.colors)
    color_map = {}

    for lane_index, lane in enumerate(lanes):
        lane_groups = [g for g in groups if g[3] == lane]
        n = len(lane_groups)
        for idx, (cost, cpu, compiler, _, vals) in enumerate(lane_groups):
            pos = lane_index + (idx - (n - 1) / 2) * (0.9 / max(n, 1))
            positions.append(pos)
            data.append(vals)
            key = (cost, cpu, compiler)
            if key not in color_map:
                color_map[key] = next(palette)
            colors.append(color_map[key])
            labels.append(f"{cost} | {cpu} | {compiler}")

    bp = ax.boxplot(data, positions=positions, widths=box_width, patch_artist=True, showfliers=True)
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.8)
    for med in bp["medians"]:
        med.set_color("black")
        med.set_linewidth(1.3)

    ax.set_xticks(range(len(lanes)))
    ax.set_xticklabels(lanes, rotation=15, ha="right")
    ax.set_ylabel("us")
    ax.set_title(f"{variant} — raw timing box plot (all cost models, cpu, compiler)")
    ax.grid(axis="y", linestyle=":", alpha=0.5)

    # Legend proxies: one entry per (cost_model, cpu, compiler)
    legend_items = []
    legend_labels = []
    seen = set()
    for (cost, cpu, compiler), color in color_map.items():
        lbl = f"{cost} | {cpu} | {compiler}"
        if lbl in seen:
            continue
        seen.add(lbl)
        legend_items.append(plt.Line2D([0], [0], color=color, lw=8))
        legend_labels.append(lbl)

    ax.legend(legend_items, legend_labels, title="cost | cpu | compiler", fontsize=7, ncol=2, loc="upper right")

    fig.tight_layout()
    out_path = out_dir / f"box_{variant}_raw_all.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def plot_summary_grouped(df, variant, cost_model, metric, out_dir, log_scale, combined=False):
    sub = df[(df.variant == variant) & ((df.cost_model == cost_model) if not combined else True)].copy()
    if sub.empty:
        return None
    lanes = sorted(sub["lane"].unique(), key=lane_key)
    sub["combo"] = sub["cpu"].astype(str) + " / " + sub["compiler"].astype(str) + (" / " + sub["cost_model"].astype(str) if combined else "")
    combos = sorted(sub["combo"].unique())
    x = np.arange(len(lanes))
    width = 0.8 / max(len(combos), 1)
    is_ratio = metric == "ratio_vs_f"

    fig, ax = plt.subplots(figsize=(max(12, 2.6 * len(lanes)), 6.5))
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
            kwargs.update(yerr=[lo, hi], capsize=2)
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
    title += " — all cost models" if combined else f" — {cost_model}"
    ax.set_title(title)
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    ax.legend(title="cpu / compiler" if not combined else "cpu / compiler / cost_model", fontsize=7, ncol=2)
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
    ap.add_argument("--combine-cost-models", action="store_true")
    ap.add_argument("--boxplot", action="store_true",
                    help="Use raw_data_*.txt files and draw real box plots from the timing points.")
    args = ap.parse_args()

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_df, raw_df = collect_data(args.results_dirs)
    if not summary_df.empty:
        summary_df.to_csv(args.csv_out, index=False)

    variants = args.variants or sorted(set(summary_df["variant"]) if not summary_df.empty else set(raw_df["variant"]))

    if args.boxplot:
        if raw_df.empty:
            raise SystemExit("No raw_data_*.txt files parsed.")
        made = 0
        for variant in variants:
            p = plot_boxplots(raw_df, variant, out_dir)
            if p:
                print(f"wrote {p}")
                made += 1
        print(f"done: {made} boxplot figure(s)")
        return

    if summary_df.empty:
        raise SystemExit("No summary bench_source.*.txt files parsed.")

    made = 0
    if args.combine_cost_models:
        for variant in variants:
            p = plot_summary_grouped(summary_df, variant, "all_cost_models", args.metric, out_dir, not args.no_log_scale, combined=True)
            if p:
                print(f"wrote {p}")
                made += 1
    else:
        cost_models = args.cost_models or sorted(summary_df.cost_model.unique())
        for variant in variants:
            for cm in cost_models:
                p = plot_summary_grouped(summary_df, variant, cm, args.metric, out_dir, not args.no_log_scale, combined=False)
                if p:
                    print(f"wrote {p}")
                    made += 1

    print(f"done: {made} figure(s)")


if __name__ == "__main__":
    main()