#!/usr/bin/env python3
"""CloudSC timing plotter.

Supports:
  1) summary files: bench_source.<compiler>_<cpu>_<cost_model>.txt
  2) raw files:     raw_data_<variant>_<cost_model>_<compiler>.txt

Boxplot mode (--boxplot) reads the raw files and makes one large figure per
variant with one box for every combination of:
  - cost model
  - cpu (inferred from parent results directory)
  - compiler
  - lane

This is intended to yield ~24 box plots per kernel when all combinations are
present.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SUMMARY_FILE_RE = re.compile(r"^bench_source\.(?P<meta>.+)\.txt$")
RAW_FILE_RE = re.compile(r"^raw_data_(?P<variant>.+)_(?P<cost_model>[^_]+)_(?P<compiler>[^_]+)\.txt$")
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
COST_ORDER = ["cheap", "default", "unlimited", "disabled"]


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


def parse_summary_file(path: pathlib.Path, cpu_tag: str):
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
            "cpu": cpu_tag,
            "compiler": compiler,
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


def parse_raw_file(path: pathlib.Path, cpu_tag: str):
    m = RAW_FILE_RE.match(path.name)
    if not m:
        return []
    variant = m.group("variant")
    cost_model = m.group("cost_model")
    compiler = m.group("compiler")
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
            "cpu": cpu_tag,
            "compiler": compiler,
            "cost_model": cost_model,
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
        cpu_tag = cpu_from_dir(d)
        for f in sorted(d.glob("bench_source.*.txt")):
            summary_rows.extend(parse_summary_file(f, cpu_tag))
        for f in sorted(d.glob("raw_data_*.txt")):
            raw_rows.extend(parse_raw_file(f, cpu_tag))
    return pd.DataFrame(summary_rows), pd.DataFrame(raw_rows)


def lane_key(lane):
    return LANE_ORDER.index(lane) if lane in LANE_ORDER else len(LANE_ORDER)


def plot_boxplots(raw_df, variant, out_dir):
    sub = raw_df[raw_df["variant"] == variant].copy()
    if cost_model is not None:
        sub = sub[sub["cost_model"] == cost_model]
    if sub.empty:
        return None

    lanes = sorted(sub["lane"].unique(), key=lane_key)
    combos = sorted(sub[["cpu", "compiler", "cost_model"]].drop_duplicates().itertuples(index=False, name=None))

    # One figure, 24-ish boxes: for each lane, show every cpu/compiler/cost_model combo.
    fig, ax = plt.subplots(figsize=(max(18, 3.0 * len(lanes)), 8))
    n_combos = len(combos)
    width = 0.8 / max(n_combos, 1)
    x = np.arange(len(lanes))

    color_cycle = plt.cm.tab20.colors
    color_map = {}
    box_data = []
    positions = []
    box_colors = []
    legend_items = []
    legend_labels = []

    for lane_idx, lane in enumerate(lanes):
        lane_groups = []
        for combo in combos:
            cpu, compiler, cost_model = combo
            vals = sub[
                (sub["lane"] == lane) &
                (sub["cpu"] == cpu) &
                (sub["compiler"] == compiler) &
                (sub["cost_model"] == cost_model)
            ]["us"].tolist()
            if vals:
                lane_groups.append((combo, vals))
        n_lane = len(lane_groups)
        for i, (combo, vals) in enumerate(lane_groups):
            pos = lane_idx + (i - (n_lane - 1) / 2) * (0.9 / max(n_lane, 1))
            positions.append(pos)
            box_data.append(vals)
            if combo not in color_map:
                color_map[combo] = color_cycle[len(color_map) % len(color_cycle)]
            box_colors.append(color_map[combo])

    if not box_data:
        return None

    bp = ax.boxplot(box_data, positions=positions, widths=width * 0.9, patch_artist=True, showfliers=True)
    for patch, color in zip(bp["boxes"], box_colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.80)
    for med in bp["medians"]:
        med.set_color("black")
        med.set_linewidth(1.3)

    ax.set_xticks(x)
    ax.set_xticklabels(lanes, rotation=15, ha="right")
    ax.set_ylabel("us")
    ax.set_title(f"{variant} — raw timing box plot")
    ax.grid(axis="y", linestyle=":", alpha=0.5)

    # Legend: one entry per distinct cpu/compiler/cost_model combination.
    for combo, color in color_map.items():
        cpu, compiler, cost_model = combo
        legend_items.append(plt.Line2D([0], [0], color=color, lw=8))
        legend_labels.append(f"{cpu} | {compiler} | {cost_model}")

    ax.legend(legend_items, legend_labels, title="cpu | compiler | cost_model", fontsize=7, ncol=2, loc="upper right")

    fig.tight_layout()
    out_path = out_dir / f"box_{variant}_raw_all.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dirs", nargs="+", default=["timing_results_eiger", "timing_results_daint"])
    ap.add_argument("--boxplot", action="store_true", help="Use raw_data_*.txt files and draw box plots.")
    ap.add_argument("--out-dir", default="plots")
    ap.add_argument("--variants", nargs="*", default=None)
    ap.add_argument("--cost-model", choices=("cheap", "default", "unlimited", "disabled"), default=None, help="Only include one cost model in boxplot mode.")
    args = ap.parse_args()

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_df, raw_df = collect_data(args.results_dirs)

    if args.boxplot:
        if raw_df.empty:
            raise SystemExit("No raw_data_*.txt files parsed.")
        variants = args.variants or sorted(raw_df["variant"].unique())
        made = 0
        for variant in variants:
            p = plot_boxplots(raw_df, variant, out_dir, cost_model=args.cost_model)
            if p:
                print(f"wrote {p}")
                made += 1
        print(f"done: {made} boxplot figure(s)")
        return

    raise SystemExit("This version is focused on --boxplot mode for the raw timing data.")


if __name__ == "__main__":
    main()