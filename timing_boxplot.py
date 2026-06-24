#!/usr/bin/env python3
"""
plot_kernel_boxplots.py
-----------------------
Reads all timing_report.csv files from a results directory tree and produces
box-plot PNGs per kernel × precision, with DaCe and CPP backends shown
side-by-side on the SAME graph.

One plot is produced per (kernel, precision) combination, e.g.:
  ecrad_clamped_reduction_float.png
  ecrad_clamped_reduction_double.png

X-axis categories are compiler_cpu_costmodel combinations
(e.g. clang_apple_m_series_cheap).
Within each x-category: CPP (blue) and DaCe (orange) are side-by-side.

Expected directory layout:
  results_cpp/<tsvc_version>/<precision>/<compiler>_<cpu>_<cost_model>/timing_report.csv
  results_dace/<tsvc_version>/<precision>/<compiler>_<cpu>_<cost_model>/timing_report.csv

  where <precision> is the folder name "float" or "double".
  Kernel names inside the CSV may carry a trailing _f or _d suffix —
  these are stripped so float and double variants of the same kernel
  share the same base name.

Usage
-----
  python3 plot_kernel_boxplots.py \
      --results-cpp  results_cpp/tsvc_2_5 \
      --results-dace results_dace/tsvc_2_5 \
      --out-dir      plots/tsvc_2_5

Optional flags
--------------
  --backend   cpp | dace | both   (default: both)
  --kernels   space-separated kernel names to plot (default: all)
  --fmt       png | pdf | svg     (default: png)
  --width     figure width in px  (default: 1400)
  --height    figure height in px (default: 700)
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio


# ── Plotly theme ───────────────────────────────────────────────────────────────
try:
    pio.templates.default = "perplexity"
except Exception:
    pio.templates.default = "plotly_white"


# CPP = blue, DaCe = orange
_BACKEND_COLOR = {
    "cpp":  "#636EFA",
    "dace": "#EF553B",
}


def _hex_to_rgba(h: str, a: float = 0.4) -> str:
    h = h.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{a})"


def _strip_precision_suffix(name: str) -> str:
    """
    Remove trailing _f or _d precision suffixes from kernel names so that
    e.g. 'ecrad_clamped_reduction_f' and 'ecrad_clamped_reduction' both
    map to the base name 'ecrad_clamped_reduction'.
    The directory-derived 'precision' column is the canonical precision label.
    """
    if name.endswith("_f"):
        return name[:-2]
    if name.endswith("_d"):
        return name[:-2]
    return name


# ── CSV discovery ──────────────────────────────────────────────────────────────
def _discover_csvs(root: pathlib.Path, backend_tag: str) -> pd.DataFrame:
    """
    Walk root recursively for timing_report.csv files.

    Expected relative path from root:
      <precision>/<compiler>_<cpu>_<cost_model>/timing_report.csv   (3 parts)

    The <precision> folder name ("float" or "double") is used as the
    canonical precision label — NOT the _f/_d suffix in kernel names.
    """
    rows = []
    for csv_path in sorted(root.rglob("timing_report.csv")):
        parts = csv_path.relative_to(root).parts  # e.g. ("float", "clang_apple_m_series_cheap", "timing_report.csv")

        if len(parts) == 3:
            precision, combo = parts[0], parts[1]
        elif len(parts) == 2:
            precision, combo = "unknown", parts[0]
        else:
            # Unexpected depth — skip
            continue

        # Only accept float / double precision folders
        if precision not in ("float", "double"):
            continue

        try:
            df = pd.read_csv(csv_path)
        except Exception as exc:
            print(f"[warn] could not read {csv_path}: {exc}", file=sys.stderr)
            continue

        df.columns = [c.strip() for c in df.columns]

        # Convert ns → µs if needed
        if "median_ns" in df.columns:
            df = df.rename(columns={
                "median_ns": "median_us",
                "min_ns":    "min_us",
                "stdev_ns":  "stdev_us",
            })
            df["median_us"] /= 1_000
            df["min_us"]    /= 1_000
            df["stdev_us"]  /= 1_000

        required = {"kernel", "median_us", "min_us", "stdev_us"}
        if not required.issubset(df.columns):
            print(f"[warn] missing columns in {csv_path}, skipping", file=sys.stderr)
            continue

        # Drop zero-time rows (un-executed kernels)
        df = df[df["median_us"] > 0].copy()
        if df.empty:
            continue

        # Normalise kernel names: strip _f / _d suffix so float & double
        # variants share the same base name. Precision comes from the folder.
        df["kernel"] = df["kernel"].apply(_strip_precision_suffix)

        df["precision"] = precision
        df["combo"]     = combo
        df["backend"]   = backend_tag

        rows.append(df[["kernel", "median_us", "min_us", "stdev_us",
                         "precision", "combo", "backend"]])

    if not rows:
        return pd.DataFrame()

    result = pd.concat(rows, ignore_index=True)
    print(f"  [{backend_tag}] found {len(result)} rows across "
          f"{result['precision'].nunique()} precision(s), "
          f"{result['combo'].nunique()} config(s), "
          f"{result['kernel'].nunique()} kernel(s)")
    return result


# ── Synthesise y-values from summary statistics ────────────────────────────────
def _synth_y(row: pd.Series) -> list:
    med = row["median_us"]
    mn  = row["min_us"]
    sd  = row["stdev_us"] if row["stdev_us"] > 0 else med * 0.05
    q1  = max(mn, med - 0.674 * sd)
    q3  = med + 0.674 * sd
    return [mn, q1, med, q3, med + 1.5 * sd]


# ── Plot one (kernel, precision) — CPP + DaCe on the same graph ───────────────
def plot_kernel_precision(
    kernel: str,
    precision: str,
    data: pd.DataFrame,
    out_dir: pathlib.Path,
    fmt: str,
    width: int,
    height: int,
) -> pathlib.Path | None:

    sub = data[
        (data["kernel"] == kernel) & (data["precision"] == precision)
    ].copy()
    if sub.empty:
        return None

    # Verify at least one backend is present
    backends_present = sub["backend"].unique()
    if len(backends_present) == 0:
        return None

    # ── X-axis ordering: clang before gcc, cost models in fixed order ──────────
    cost_order = {"cheap": 0, "default": 1, "disabled": 2, "unlimited": 3}

    def _sort_key(combo: str) -> tuple:
        tok = combo.split("_")
        compiler = tok[0]        # clang / gcc
        cost     = tok[-1]       # cheap / default / disabled / unlimited
        return (compiler, cost_order.get(cost, 99))

    x_categories = sorted(sub["combo"].unique(), key=_sort_key)

    # Determine display unit from overall max
    med_max = sub["median_us"].max()
    scale, unit = (1_000, "ms") if med_max >= 1_000 else (1, "µs")

    fig = go.Figure()

    # ── Two traces per graph: CPP (blue) and DaCe (orange) ────────────────────
    for backend in ("cpp", "dace"):
        b_sub = sub[sub["backend"] == backend]
        if b_sub.empty:
            continue

        color = _BACKEND_COLOR[backend]

        x_vals, y_vals = [], []
        for x_cat in x_categories:
            for _, row in b_sub[b_sub["combo"] == x_cat].iterrows():
                pts = _synth_y(row)
                x_vals.extend([x_cat] * len(pts))
                y_vals.extend([v / scale for v in pts])

        if not x_vals:
            continue

        fig.add_trace(go.Box(
            x=x_vals,
            y=y_vals,
            name=backend.upper(),
            marker_color=color,
            fillcolor=_hex_to_rgba(color, 0.4),
            line=dict(color=color, width=1.8),
            boxpoints=False,
            offsetgroup=backend,   # side-by-side within each x-category
        ))

    fig.update_layout(
        boxmode="group",
        title=dict(
            text=(
                f"{kernel}  [{precision}]<br>"
                "<span style='font-size:14px;font-weight:normal;'>"
                "CPP (blue) vs DaCe (orange) — execution time by compiler / cpu / cost model"
                "</span>"
            ),
            font_size=20,
        ),
        legend=dict(
            title_text="Backend",
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
        width=width,
        height=height,
        xaxis=dict(
            title_text="Compiler / CPU / Cost model",
            tickangle=-35,
            automargin=True,
            categoryorder="array",
            categoryarray=x_categories,
        ),
        yaxis=dict(title_text=f"Time ({unit})"),
        margin=dict(b=180),
    )

    safe_kernel    = re.sub(r"[^a-zA-Z0-9_-]", "_", kernel)
    safe_precision = re.sub(r"[^a-zA-Z0-9_-]", "_", precision)
    out_path = out_dir / f"{safe_kernel}_{safe_precision}.{fmt}"
    fig.write_image(str(out_path))

    meta = {
        "caption": f"{kernel} [{precision}] — CPP vs DaCe execution time by config",
        "description": (
            f"Grouped box plot of {kernel} ({precision}) execution time "
            "(median/min/stdev). CPP (blue) and DaCe (orange) are shown "
            "side-by-side for each compiler/cpu/cost-model combination."
        ),
    }
    (out_dir / f"{safe_kernel}_{safe_precision}.{fmt}.meta.json").write_text(
        json.dumps(meta, indent=2)
    )
    return out_path


# ── CLI ────────────────────────────────────────────────────────────────────────
def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Per-kernel box-plot sweep visualiser.")
    ap.add_argument("--results-cpp",  default=None, metavar="DIR")
    ap.add_argument("--results-dace", default=None, metavar="DIR")
    ap.add_argument("--backend", default="both", choices=["cpp", "dace", "both"])
    ap.add_argument("--out-dir", default="plots", metavar="DIR")
    ap.add_argument("--kernels", nargs="*", default=None, metavar="KERNEL")
    ap.add_argument("--fmt", default="png", choices=["png", "pdf", "svg"])
    ap.add_argument("--width",  type=int, default=1400, metavar="PX")
    ap.add_argument("--height", type=int, default=700,  metavar="PX")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    frames = []

    if args.backend in ("cpp", "both") and args.results_cpp:
        cpp_root = pathlib.Path(args.results_cpp)
        if cpp_root.is_dir():
            df = _discover_csvs(cpp_root, "cpp")
            if not df.empty:
                frames.append(df)
        else:
            print(f"[warn] --results-cpp path not found: {cpp_root}", file=sys.stderr)

    if args.backend in ("dace", "both") and args.results_dace:
        dace_root = pathlib.Path(args.results_dace)
        if dace_root.is_dir():
            df = _discover_csvs(dace_root, "dace")
            if not df.empty:
                frames.append(df)
        else:
            print(f"[warn] --results-dace path not found: {dace_root}", file=sys.stderr)

    if not frames:
        print("ERROR: no timing data found. Check --results-cpp / --results-dace paths.",
              file=sys.stderr)
        return 1

    # Both CPP and DaCe data are now in a single combined DataFrame
    data = pd.concat(frames, ignore_index=True)

    print(f"\nCombined dataset: {len(data)} rows, "
          f"{data['kernel'].nunique()} kernels, "
          f"{data['precision'].nunique()} precision(s), "
          f"{data['backend'].nunique()} backend(s): {sorted(data['backend'].unique())}")

    kernels    = args.kernels if args.kernels else sorted(data["kernel"].unique())
    precisions = [p for p in ("float", "double") if p in data["precision"].values]

    print(f"Plotting {len(kernels)} kernels × {len(precisions)} precisions "
          f"= up to {len(kernels) * len(precisions)} plots ...\n")

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    for kernel in kernels:
        for precision in precisions:
            path = plot_kernel_precision(
                kernel=kernel,
                precision=precision,
                data=data,
                out_dir=out_dir,
                fmt=args.fmt,
                width=args.width,
                height=args.height,
            )
            if path:
                print(f"  ✓ {path.name}")
                generated += 1
            else:
                print(f"  – {kernel} [{precision}]: no data, skipped")

    print(f"\nDone — {generated} plots saved to {out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())