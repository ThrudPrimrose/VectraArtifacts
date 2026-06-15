"""
vectorization_heatmap.py

Reads vec_report.txt files produced by the vectorization sweep and generates
three side-by-side heatmaps (one per cost model) showing the percentage of
TSVC-2 kernels vectorized for each compiler x CPU combination.

Expected directory layout:
  <results_dir>/<compiler>_<cpu_arch>_<cost_model>/vec_report.txt

  e.g.  results_cpp/clang_apple_m_series_default/vec_report.txt
        results_cpp/gcc_apple_m_series_cheap/vec_report.txt

Usage:
  python3 vectorization_heatmap.py
  python3 vectorization_heatmap.py --results-dir results_dace --out heatmap_dace.png

Requirements:
  pip install plotly kaleido
"""

import argparse
import json
import pathlib
import re

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ── Configuration ──────────────────────────────────────────────────────────────
COMPILERS   = ["clang", "gcc"]
# CPU_ARCHS   = [
#     "apple_m_series",
#     "arm_grace",
#     "amd_epyc",
#     "amd_epyc_genoa",
#     "intel_xeon",
#     "ibm_power",
#     "fugaku_a64fx",
# ]
CPU_ARCHS   = ["apple_m_series",]
COST_MODELS = ["default", "cheap", "unlimited", "disabled"]

# Short x-axis labels (must match CPU_ARCHS order)
# CPU_LABELS  = ["apple_m", "arm_grace", "amd_epyc", "epyc_genoa",
#                "intel_xeon", "ibm_power", "a64fx"]
CPU_LABELS  = ["apple_m", ]

# Display names for compilers (y-axis)
COMPILER_LABELS = {"clang": "Clang", "gcc": "GCC"}


# ── Helpers ────────────────────────────────────────────────────────────────────
def load_vec_rate(results_root: pathlib.Path, name: str) -> float:
    """Return % kernels vectorized from vec_report.txt, or NaN if missing."""
    rpt = results_root / name / "vec_report.txt"
    if not rpt.exists():
        return float("nan")
    text = rpt.read_text()
    m = re.search(r"(\d+)/(\d+)\s+kernels\s+vectorized", text, re.IGNORECASE)
    if m:
        numerator = int(m.group(1))
        denominator = int(m.group(2))
        if denominator == 0:
            return float("nan")
        if numerator == 0:
            return 0.0
        return round(100 * numerator / denominator, 1)
    return float("nan")


def build_matrix(results_root: pathlib.Path, cost_model: str):
    """Return (z, text) matrices: rows=compilers, cols=cpu_archs."""
    z, text = [], []
    for comp in COMPILERS:
        row_z, row_t = [], []
        for cpu in CPU_ARCHS:
            name = f"{comp}_{cpu}_{cost_model}"
            v = load_vec_rate(results_root, name)
            row_z.append(v)
            if isinstance(v, float) and np.isnan(v):
                row_t.append("N/A")
            else:
                row_t.append(f"{v}%")
        z.append(row_z)
        text.append(row_t)
    return z, text


def add_heatmap(fig, z, text, row, col, title, showscale=False):
    y_labels = [COMPILER_LABELS.get(c, c) for c in COMPILERS]
    fig.add_trace(
        go.Heatmap(
            z=z,
            x=CPU_LABELS,
            y=y_labels,
            colorscale="RdYlGn",
            zmin=0,
            zmax=100,
            showscale=showscale,
            colorbar=dict(
                title=dict(text="% Vectorized", side="right"),
                x=1.02,
                thickness=15,
                len=0.85,
            ) if showscale else None,
            text=text,
            texttemplate="%{text}",
            textfont=dict(size=14, color="black"),
            hovertemplate=(
                "Compiler: %{y}<br>CPU: %{x}<br>"
                "Vectorized: %{z:.1f}%<extra></extra>"
            ),
        ),
        row=row,
        col=col,
    )


# ── Main plot function ─────────────────────────────────────────────────────────
def make_heatmaps(
    cpp_root: pathlib.Path,
    dace_root: pathlib.Path,
    out_dir: pathlib.Path,
):
    out_dir.mkdir(parents=True, exist_ok=True)
    output_paths = []

    for cm in COST_MODELS:
        fig = make_subplots(
            rows=1,
            cols=2,
            subplot_titles=["C++ Kernels", "DaCe Kernels"],
            horizontal_spacing=0.18,
        )

        # Left panel — C++
        z_cpp, text_cpp = build_matrix(cpp_root, cm)
        add_heatmap(fig, z_cpp, text_cpp, row=1, col=1, title="C++", showscale=False)

        # Right panel — DaCe
        z_dace, text_dace = build_matrix(dace_root, cm)
        add_heatmap(fig, z_dace, text_dace, row=1, col=2, title="DaCe", showscale=True)

        fig.update_layout(
            title={
                "text": (
                    f"Vectorization Rate — Cost Model: <b>{cm.upper()}</b><br>"
                    "<span style=\'font-size:15px;font-weight:normal;\'>"
                    "% of TSVC-2 kernels vectorized per compiler &amp; CPU"
                    "</span>"
                ),
                "x": 0.5,
                "xanchor": "center",
            },
            height=380,
            width=900,
            margin=dict(t=110, b=80, l=80, r=100),
            font=dict(family="Inter, Arial, sans-serif", size=13),
            paper_bgcolor="#f9f8f5",
            plot_bgcolor="#f9f8f5",
        )

        for col_idx in range(1, 3):
            fig.update_xaxes(
                title_text="CPU Architecture",
                row=1,
                col=col_idx,
                tickangle=30,
            )
        fig.update_yaxes(title_text="Compiler", row=1, col=1)
        fig.update_yaxes(title_text="Compiler", row=1, col=2)

        out_path = out_dir / f"heatmap_{cm}.png"
        fig.write_image(str(out_path))
        print(f"Saved -> {out_path.resolve()}")
        output_paths.append(out_path)

        meta = out_path.with_suffix(out_path.suffix + ".meta.json")
        meta.write_text(json.dumps({
            "caption": f"Vectorization Rate Heatmap — Cost Model: {cm}",
            "description": (
                f"Side-by-side heatmap comparing C++ and DaCe vectorization rates "
                f"for cost model \'{cm}\'. Rows = compilers, cols = CPU architectures. "
                f"Values are % of TSVC-2 kernels vectorized."
            ),
        }))

    return output_paths


# ── Entry point ────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="Generate per-cost-model vectorization heatmaps (CPP vs DaCe)."
    )
    ap.add_argument(
        "--cpp-dir",
        default="results_cpp",
        metavar="DIR",
        help="Root folder for C++ results (default: results_cpp).",
    )
    ap.add_argument(
        "--dace-dir",
        default="results_dace",
        metavar="DIR",
        help="Root folder for DaCe results (default: results_dace).",
    )
    ap.add_argument(
        "--out-dir",
        default="heatmaps",
        metavar="DIR",
        help="Output directory for PNG files (default: heatmaps/).",
    )
    args = ap.parse_args()

    cpp_root  = pathlib.Path(args.cpp_dir)
    dace_root = pathlib.Path(args.dace_dir)

    for d, name in [(cpp_root, "--cpp-dir"), (dace_root, "--dace-dir")]:
        if not d.exists():
            raise SystemExit(f"ERROR: results directory not found: {d!r} ({name})")

    make_heatmaps(cpp_root, dace_root, pathlib.Path(args.out_dir))


if __name__ == "__main__":
    main()
