import re, json, os
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ROOT = "cloudsc_variants"
SKIP_DIRS = {"harness"}
COST_MODEL_ORDER = ["cheap", "default", "unlimited", "disabled"]
COMPILER_ORDER = ["clang", "gcc"]
FRONTEND_ORDER = ["python", "fortran", "f90"]
CPU_ORDER = ["amd_epyc", "amd_epyc_genoa", "arm_grace", "apple_m_series",
             "fugaku_a64fx", "ibm_power", "intel_xeon"]
COLOR_MAP = {"clang": "#4C78A8", "gcc": "#F58518", "f90": "#26EB47"}

# Matches e.g. clang_amd_epyc_default, gcc_arm_grace_cheap, clang_amd_epyc_genoa_unlimited
CELL_RE = re.compile(
    r'^(clang|gcc|icpx)_(.+)_(cheap|default|unlimited|disabled)$'
)


def parse_report(text, frontend_label):
    rows = []
    kernel_blocks = re.split(r'\n(?=Benchmark:)', text.strip())
    for kblock in kernel_blocks:
        kmatch = re.search(r'Benchmark:\s*(\S+)', kblock)
        if not kmatch:
            continue
        kernel = kmatch.group(1)
        sections = re.split(r'\n(?===+ \S+ ===+)', kblock)
        clang_totals = {}
        entries = []
        for sec in sections:
            hmatch = re.search(r'===+\s*(\S+)\s*===+', sec)
            if not hmatch:
                continue
            name = hmatch.group(1)
            m = CELL_RE.match(name)
            if not m:
                continue
            compiler, cpu, cost_model = m.group(1), m.group(2), m.group(3)
            lc = re.search(r'Loop counts:\s*(\d+)/(\d+)\s*loops vectorized', sec)
            vec, tot = (int(lc.group(1)), int(lc.group(2))) if lc else (0, None)
            entries.append((compiler, cpu, cost_model, vec, tot))
            if compiler == 'clang' and tot is not None:
                clang_totals[cpu] = tot if cpu not in clang_totals else max(clang_totals[cpu], tot)
        if not clang_totals:
            continue
        for compiler, cpu, cost_model, vec, tot in entries:
            total_for_cpu = clang_totals.get(cpu, max(clang_totals.values()))
            rows.append({'kernel': kernel, 'frontend': frontend_label, 'compiler': compiler,
                          'cpu': cpu, 'cost_model': cost_model, 'vectorized': vec,
                          'total_loops': total_for_cpu})
    return rows


def parse_fortran_baseline(text):
    """Extract embedded '--- Fortran baseline ---' sections from a report file."""
    rows = []
    kernel_blocks = re.split(r'\n(?=Benchmark:)', text.strip())
    for kblock in kernel_blocks:
        kmatch = re.search(r'Benchmark:\s*(\S+)', kblock)
        if not kmatch:
            continue
        kernel = kmatch.group(1)
        fort_sections = re.split(r'\n(?=--- Fortran baseline)', kblock)
        for sec in fort_sections[1:]:
            cell_m = re.search(r'\[([^\]]+)\]', sec)
            if not cell_m:
                continue
            cell = cell_m.group(1)
            m = CELL_RE.match(cell)
            if not m:
                continue
            compiler, cpu, cost_model = m.group(1), m.group(2), m.group(3)
            lc = re.search(r'Loop counts:\s*(\d+)/(\d+)\s*loops vectorized', sec)
            vec = int(lc.group(1)) if lc else 0
            rows.append({'kernel': kernel, 'frontend': 'f90', 'compiler': compiler,
                         'cpu': cpu, 'cost_model': cost_model, 'vectorized': vec, 'total_loops': None})
    return rows


def collect_all_reports(root=ROOT):
    all_rows = []
    for kernel_dir in sorted(os.listdir(root)):
        if kernel_dir in SKIP_DIRS:
            continue
        kdir_path = os.path.join(root, kernel_dir)
        if not os.path.isdir(kdir_path):
            continue
        fort_loaded = False
        for frontend in ["python", "fortran"]:
            fpath = os.path.join(kdir_path, f"vectorization_report_{kernel_dir}_{frontend}_frontend.txt")
            if os.path.exists(fpath):
                with open(fpath) as f:
                    text = f.read()
                all_rows.extend(parse_report(text, frontend))
                if not fort_loaded:
                    all_rows.extend(parse_fortran_baseline(text))
                    fort_loaded = True
            else:
                print(f"Warning: missing {fpath}")
    df = pd.DataFrame(all_rows)
    # Back-fill total_loops for f90 rows using kernel+cpu-level max from SDFG rows
    if not df.empty and 'f90' in df['frontend'].values:
        kernel_cpu_totals = (
            df[df['frontend'] != 'f90']
            .groupby(['kernel', 'cpu'])['total_loops'].max()
        )
        mask = df['frontend'] == 'f90'
        df.loc[mask, 'total_loops'] = df.loc[mask].apply(
            lambda r: kernel_cpu_totals.get((r['kernel'], r['cpu']), None), axis=1
        )
    return df


def make_kernel_chart(df, kernel, output_dir="output"):
    os.makedirs(output_dir, exist_ok=True)
    sub = df[df['kernel'] == kernel].copy()
    if sub.empty:
        return None

    cpus_present = [c for c in CPU_ORDER if c in sub['cpu'].unique()]
    if not cpus_present:
        cpus_present = sorted(sub['cpu'].unique())

    n = len(cpus_present)
    fig = make_subplots(rows=1, cols=n, subplot_titles=cpus_present,
                         shared_yaxes=True, horizontal_spacing=0.04)

    global_max_total = sub['total_loops'].max()

    for col_idx, cpu in enumerate(cpus_present, start=1):
        cpu_sub = sub[sub['cpu'] == cpu]
        total_loops = cpu_sub['total_loops'].max()

        x_labels, y_vals, colors = [], [], []
        for fe in FRONTEND_ORDER:
            for compiler in COMPILER_ORDER:
                for cm in COST_MODEL_ORDER:
                    row = cpu_sub[(cpu_sub['frontend']==fe)&(cpu_sub['compiler']==compiler)&(cpu_sub['cost_model']==cm)]
                    x_labels.append(f"{fe[:2].upper()}_{compiler}_{cm}")
                    y_vals.append(int(row['vectorized'].values[0]) if not row.empty else 0)
                    colors.append(COLOR_MAP["f90"] if fe == "f90" else COLOR_MAP[compiler])

        fig.add_trace(
            go.Bar(x=x_labels, y=y_vals, marker_color=colors,
                   text=[str(v) for v in y_vals], textposition='outside', width=0.6,
                   showlegend=False),
            row=1, col=col_idx
        )
        if pd.notna(total_loops):
            fig.add_hline(y=total_loops, line_dash="dash", line_color="gray",
                          annotation_text=f"Total = {int(total_loops)}",
                          annotation_position="top left",
                          row=1, col=col_idx)

    fig.add_trace(go.Bar(x=[None], y=[None], marker_color=COLOR_MAP["clang"], name="Clang"), row=1, col=1)
    fig.add_trace(go.Bar(x=[None], y=[None], marker_color=COLOR_MAP["gcc"],   name="GCC"), row=1, col=1)
    fig.add_trace(go.Bar(x=[None], y=[None], marker_color=COLOR_MAP["f90"],   name="Fortran baseline"), row=1, col=1)

    fig.update_layout(
        title={"text": f"Loops Vectorized — {kernel} (by CPU architecture)"},
        legend=dict(orientation='h', yanchor='bottom', y=1.08, xanchor='center', x=0.5),
        bargap=0.25,
        width=max(900, 700 * n),
        height=750,
    )
    fig.update_xaxes(tickangle=-45, type='category')
    fig.update_yaxes(title_text="Loops vectorized", range=[0, global_max_total*1.2 if pd.notna(global_max_total) else 1], col=1)
    fig.update_traces(cliponaxis=False)

    out_name = os.path.join(output_dir, f"vectorization_{kernel}.png")
    fig.write_image(out_name, width=fig.layout.width, height=fig.layout.height)
    with open(out_name + ".meta.json", "w") as f:
        json.dump({"caption": f"Raw loops vectorized — {kernel}",
                    "description": f"Column charts of vectorized loop counts by frontend/compiler/cost-model, faceted by CPU architecture ({', '.join(cpus_present)}) for {kernel}."}, f)
    return out_name


df = collect_all_reports(ROOT)
for kernel in df['kernel'].unique():
    make_kernel_chart(df, kernel)