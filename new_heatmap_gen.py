"""
vectorization_heatmap.py

Reads vec_report.txt files produced by the vectorization sweep and generates
side-by-side heatmaps (one per cost model) showing the percentage of kernels
vectorized for each compiler x CPU combination.

Expected directory layout (run_sweep.py output):
  <results_dir>/<tsvc_version>/[precision/]<compiler>_<cpu>_<cost_model>/vec_report.txt

  e.g.  results_cpp/tsvc_2/clang_apple_m_series_default/vec_report.txt          (single precision)
        results_cpp/tsvc_2/double/clang_apple_m_series_default/vec_report.txt   (--precision both)
        results_cpp/tsvc_2_5/clang_apple_m_series_default/vec_report.txt

Usage:
  python3 vectorization_heatmap.py                                         # defaults
  python3 vectorization_heatmap.py --tsvc-version tsvc_2_5                # different version
  python3 vectorization_heatmap.py --precision float                       # float variants
  python3 vectorization_heatmap.py --compilers clang gcc --cpus intel_xeon amd_epyc
  python3 vectorization_heatmap.py --cost-models default cheap             # subset of cost models
  python3 vectorization_heatmap.py --cpp-dir results_cpp --dace-dir results_dace --out-dir heatmaps

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


# ── Valid choices (mirrors run_sweep.py) ──────────────────────────────────────
ALL_COMPILERS   = ["clang", "gcc", "icpx"]
ALL_COST_MODELS = ["default", "cheap", "unlimited", "disabled"]
ALL_CPUS        = [
    "amd_epyc", "amd_epyc_genoa", "apple_m_series",
    "arm_grace", "fugaku_a64fx", "ibm_power", "intel_xeon",
]
ALL_VERSIONS    = ["tsvc_2", "tsvc_2_5"]
ALL_PRECISIONS  = ["double", "float"]

# Short display labels for CPU axes
CPU_SHORT_LABELS = {
    "apple_m_series":  "apple_m",
    "arm_grace":       "arm_grace",
    "amd_epyc":        "amd_epyc",
    "amd_epyc_genoa":  "epyc_genoa",
    "intel_xeon":      "intel_xeon",
    "ibm_power":       "ibm_power",
    "fugaku_a64fx":    "a64fx",
}

# Display labels for compilers
COMPILER_LABELS = {"clang": "Clang", "gcc": "GCC", "icpx": "ICPX"}


# ── Result directory resolution ───────────────────────────────────────────────
def _results_root(base_dir: pathlib.Path, tsvc_version: str, precision: str) -> pathlib.Path:
    """Compute the folder that contains <compiler>_<cpu>_<cost_model>/ subdirs.

    run_sweep.py writes results to one of two layouts depending on --precision:

      Single precision (--precision double OR --precision float):
        <base_dir>/<tsvc_version>/<compiler>_<cpu>_<cost_model>/vec_report.txt

      Both precisions (--precision both):
        <base_dir>/<tsvc_version>/<precision>/<compiler>_<cpu>_<cost_model>/vec_report.txt

    We probe both and return whichever exists.
    """
    # Try the "both" layout first (has a precision subdirectory)
    with_prec = base_dir / tsvc_version / precision
    if with_prec.exists():
        return with_prec

    # Fall back to the single-precision layout (no precision subdirectory)
    flat = base_dir / tsvc_version
    if flat.exists():
        return flat

    # Return the "both" path so the caller can emit a clear error
    return with_prec


# ── Data loading ──────────────────────────────────────────────────────────────
def load_vec_rate(results_root: pathlib.Path, name: str) -> float:
    """Return % kernels vectorized from vec_report.txt, or NaN if missing."""
    rpt = results_root / name / "vec_report.txt"
    if not rpt.exists():
        return float("nan")
    text = rpt.read_text()
    m = re.search(r"(\d+)/(\d+)\s+kernels\s+vectorized", text, re.IGNORECASE)
    if m:
        numerator, denominator = int(m.group(1)), int(m.group(2))
        if denominator == 0:
            return float("nan")
        return round(100 * numerator / denominator, 1)
    return float("nan")


def build_matrix(results_root: pathlib.Path, compilers: list, cpus: list, cost_model: str):
    """Return (z, text) matrices: rows=compilers, cols=cpu_archs."""
    z, text = [], []
    for comp in compilers:
        row_z, row_t = [], []
        for cpu in cpus:
            name = f"{comp}_{cpu}_{cost_model}"
            v = load_vec_rate(results_root, name)
            row_z.append(v)
            row_t.append("N/A" if (isinstance(v, float) and np.isnan(v)) else f"{v}%")
        z.append(row_z)
        text.append(row_t)
    return z, text


# ── Heatmap rendering ─────────────────────────────────────────────────────────
def add_heatmap(fig, z, text, cpu_labels, compiler_labels, row, col, showscale=False):
    fig.add_trace(
        go.Heatmap(
            z=z,
            x=cpu_labels,
            y=compiler_labels,
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


def make_heatmaps(
    cpp_root: pathlib.Path,
    dace_root: pathlib.Path,
    out_dir: pathlib.Path,
    compilers: list,
    cpus: list,
    cost_models: list,
    tsvc_version: str,
    precision: str,
):
    out_dir.mkdir(parents=True, exist_ok=True)

    cpp_results  = _results_root(cpp_root,  tsvc_version, precision)
    dace_results = _results_root(dace_root, tsvc_version, precision)

    for d, flag in [(cpp_results, "--cpp-dir"), (dace_results, "--dace-dir")]:
        if not d.exists():
            raise SystemExit(
                f"ERROR: results directory not found: {d!r}\n"
                f"  Make sure you ran run_sweep.py with --tsvc-version {tsvc_version} "
                f"and --precision {precision} (or 'both')."
            )

    cpu_labels      = [CPU_SHORT_LABELS.get(c, c) for c in cpus]
    comp_labels     = [COMPILER_LABELS.get(c, c)  for c in compilers]
    version_label   = tsvc_version.replace("_", " ").upper()
    prec_label      = precision.capitalize()

    output_paths = []
    for cm in cost_models:
        fig = make_subplots(
            rows=1,
            cols=2,
            subplot_titles=["C++ Kernels", "DaCe Kernels"],
            horizontal_spacing=0.18,
        )

        z_cpp,  text_cpp  = build_matrix(cpp_results,  compilers, cpus, cm)
        z_dace, text_dace = build_matrix(dace_results, compilers, cpus, cm)

        add_heatmap(fig, z_cpp,  text_cpp,  cpu_labels, comp_labels, row=1, col=1, showscale=False)
        add_heatmap(fig, z_dace, text_dace, cpu_labels, comp_labels, row=1, col=2, showscale=True)

        fig.update_layout(
            title={
                "text": (
                    f"Vectorization Rate — {version_label} | {prec_label} | "
                    f"Cost Model: <b>{cm.upper()}</b><br>"
                    "<span style=\'font-size:15px;font-weight:normal;\'>"
                    "% of kernels vectorized per compiler &amp; CPU"
                    "</span>"
                ),
                "x": 0.5,
                "xanchor": "center",
            },
            height=380,
            width=900,
            margin=dict(t=120, b=80, l=80, r=100),
            font=dict(family="Inter, Arial, sans-serif", size=13),
            paper_bgcolor="#f9f8f5",
            plot_bgcolor="#f9f8f5",
        )

        for col_idx in range(1, 3):
            fig.update_xaxes(title_text="CPU Architecture", row=1, col=col_idx, tickangle=30)
        fig.update_yaxes(title_text="Compiler", row=1, col=1)
        fig.update_yaxes(title_text="Compiler", row=1, col=2)

        out_path = out_dir / f"heatmap_{tsvc_version}_{precision}_{cm}.png"
        fig.write_image(str(out_path))
        print(f"Saved -> {out_path.resolve()}")
        output_paths.append(out_path)

        meta = out_path.with_suffix(".png.meta.json")
        meta.write_text(json.dumps({
            "caption": (
                f"Vectorization Rate — {version_label} | {prec_label} | "
                f"Cost Model: {cm}"
            ),
            "description": (
                f"Side-by-side heatmap (C++ vs DaCe) for {version_label}, "
                f"{prec_label} precision, cost model '{cm}'. "
                f"Rows = compilers ({', '.join(compilers)}), "
                f"cols = CPU architectures ({', '.join(cpus)}). "
                f"Values are % of kernels vectorized."
            ),
        }))

    return output_paths


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="Generate per-cost-model vectorization heatmaps (CPP vs DaCe).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
examples:
  # defaults: tsvc_2 / double / clang+gcc / apple_m_series / all cost models
  python3 vectorization_heatmap.py

  # tsvc_2_5 with float kernels
  python3 vectorization_heatmap.py --tsvc-version tsvc_2_5 --precision float

  # compare multiple compilers and CPUs, only two cost models
  python3 vectorization_heatmap.py --compilers clang gcc icpx \
      --cpus apple_m_series intel_xeon amd_epyc \
      --cost-models default disabled

  # custom result directories
  python3 vectorization_heatmap.py --cpp-dir my_cpp_results --dace-dir my_dace_results

valid compilers   : {", ".join(ALL_COMPILERS)}
valid cost-models : {", ".join(ALL_COST_MODELS)}
valid cpus        : {", ".join(ALL_CPUS)}
valid versions    : {", ".join(ALL_VERSIONS)}
valid precisions  : {", ".join(ALL_PRECISIONS)}
        """,
    )
    ap.add_argument(
        "--tsvc-version",
        default="tsvc_2",
        choices=ALL_VERSIONS,
        metavar="VERSION",
        help=f"TSVC version whose results to visualize. Choices: {', '.join(ALL_VERSIONS)}. (default: tsvc_2)",
    )
    ap.add_argument(
        "--precision",
        default="double",
        choices=ALL_PRECISIONS,
        metavar="PRECISION",
        help=f"Which precision results to visualize. Choices: {', '.join(ALL_PRECISIONS)}. (default: double)",
    )
    ap.add_argument(
        "--compilers",
        nargs="+",
        default=["clang", "gcc"],
        choices=ALL_COMPILERS,
        metavar="COMPILER",
        help=f"Compilers to show. Choices: {', '.join(ALL_COMPILERS)}. (default: clang gcc)",
    )
    ap.add_argument(
        "--cost-models",
        nargs="+",
        default=list(ALL_COST_MODELS),
        choices=ALL_COST_MODELS,
        metavar="MODEL",
        help=f"Cost models to generate heatmaps for. Choices: {', '.join(ALL_COST_MODELS)}. (default: all)",
    )
    ap.add_argument(
        "--cpus",
        nargs="+",
        default=["apple_m_series"],
        choices=ALL_CPUS,
        metavar="CPU",
        help=f"CPU architectures to show. Choices: {', '.join(ALL_CPUS)}. (default: apple_m_series)",
    )
    ap.add_argument(
        "--cpp-dir",
        default="results_cpp",
        metavar="DIR",
        help="Root folder for C++ results (default: results_cpp). Version and precision subfolders are appended automatically.",
    )
    ap.add_argument(
        "--dace-dir",
        default="results_dace",
        metavar="DIR",
        help="Root folder for DaCe results (default: results_dace). Version and precision subfolders are appended automatically.",
    )
    ap.add_argument(
        "--out-dir",
        default="heatmaps",
        metavar="DIR",
        help="Output directory for PNG + JSON meta files (default: heatmaps/).",
    )
    args = ap.parse_args()

    make_heatmaps(
        cpp_root     = pathlib.Path(args.cpp_dir),
        dace_root    = pathlib.Path(args.dace_dir),
        out_dir      = pathlib.Path(args.out_dir),
        compilers    = args.compilers,
        cpus         = args.cpus,
        cost_models  = args.cost_models,
        tsvc_version = args.tsvc_version,
        precision    = args.precision,
    )


if __name__ == "__main__":
    main()