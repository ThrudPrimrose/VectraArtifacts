import re, json, os
import pandas as pd
import plotly.graph_objects as go

ROOT = "cloudsc_variants"
SKIP_DIRS = {"harness"}
COST_MODEL_ORDER = ["cheap", "default", "unlimited", "disabled"]
COMPILER_ORDER = ["clang", "gcc"]
FRONTEND_ORDER = ["python", "fortran"]
COLOR_MAP = {"clang": "#4C78A8", "gcc": "#F58518"}

def parse_report(text, frontend_label):
    rows = []
    kernel_blocks = re.split(r'\n(?=Benchmark:)', text.strip())
    for kblock in kernel_blocks:
        kmatch = re.search(r'Benchmark:\s*(\S+)', kblock)
        if not kmatch:
            continue
        kernel = kmatch.group(1)
        sections = re.split(r'\n(?===+ \S+ ===+)', kblock)
        clang_total = None
        entries = []
        for sec in sections:
            hmatch = re.search(r'===+\s*(\S+)\s*===+', sec)
            if not hmatch:
                continue
            name = hmatch.group(1)
            m = re.match(r'(clang|gcc)_.*_(cheap|default|unlimited|disabled)$', name)
            if not m:
                continue
            compiler, cost_model = m.group(1), m.group(2)
            lc = re.search(r'Loop counts:\s*(\d+)/(\d+)\s*loops vectorized', sec)
            vec, tot = (int(lc.group(1)), int(lc.group(2))) if lc else (0, None)
            entries.append((compiler, cost_model, vec, tot))
            if compiler == 'clang' and tot is not None:
                clang_total = tot if clang_total is None else max(clang_total, tot)
        if clang_total is None:
            continue
        for compiler, cost_model, vec, tot in entries:
            rows.append({'kernel': kernel, 'frontend': frontend_label, 'compiler': compiler,
                          'cost_model': cost_model, 'vectorized': vec, 'total_loops': clang_total})
    return rows

def collect_all_reports(root=ROOT):
    all_rows = []
    for kernel_dir in sorted(os.listdir(root)):
        if kernel_dir in SKIP_DIRS:
            continue
        kdir_path = os.path.join(root, kernel_dir)
        if not os.path.isdir(kdir_path):
            continue
        for frontend in FRONTEND_ORDER:
            fpath = os.path.join(kdir_path, f"vectorization_report_{kernel_dir}_{frontend}_frontend.txt")
            if os.path.exists(fpath):
                with open(fpath) as f:
                    all_rows.extend(parse_report(f.read(), frontend))
            else:
                print(f"Warning: missing {fpath}")
    return pd.DataFrame(all_rows)

def make_kernel_chart(df, kernel, output_dir="output"):
    os.makedirs(output_dir, exist_ok=True)
    sub = df[df['kernel'] == kernel].copy()
    if sub.empty:
        return None
    total_loops = sub['total_loops'].max()

    x_labels, y_vals, colors = [], [], []
    for fe in FRONTEND_ORDER:
        for compiler in COMPILER_ORDER:
            for cm in COST_MODEL_ORDER:
                row = sub[(sub['frontend']==fe)&(sub['compiler']==compiler)&(sub['cost_model']==cm)]
                x_labels.append(f"{fe[:2].upper()}_{compiler}_{cm}")
                y_vals.append(int(row['vectorized'].values[0]) if not row.empty else 0)
                colors.append(COLOR_MAP[compiler])

    fig = go.Figure()
    fig.add_trace(go.Bar(x=x_labels, y=y_vals, marker_color=colors,
                          text=[str(v) for v in y_vals], textposition='outside', width=0.6))
    fig.add_hline(y=total_loops, line_dash="dash", line_color="gray",
                  annotation_text=f"Total = {total_loops}", annotation_position="top left")
    fig.add_trace(go.Bar(x=[None], y=[None], marker_color=COLOR_MAP["clang"], textposition='outside', name="Clang"))
    fig.add_trace(go.Bar(x=[None], y=[None], marker_color=COLOR_MAP["gcc"], textposition='outside', name="GCC"))

    fig.update_layout(
        title={"text": f"Loops Vectorized — {kernel}<br>"
                        "<span style='font-size: 18px; font-weight: normal;'>"},
        legend=dict(orientation='h', yanchor='bottom', y=1.05, xanchor='center', x=0.5),
        bargap=0.25
    )
    fig.update_xaxes(title_text="Frontend_Compiler_CostModel", tickangle=-45, type='category')
    fig.update_yaxes(title_text="Loops vectorized", range=[0, total_loops*1.2])
    fig.update_traces(cliponaxis=False)

    out_name = os.path.join(output_dir, f"vectorization_{kernel}.png")
    fig.write_image(out_name, width=1400, height=700)
    with open(out_name + ".meta.json", "w") as f:
        json.dump({"caption": f"Raw loops vectorized — {kernel}",
                    "description": f"16-category column chart of vectorized loop counts by frontend, compiler, cost model for {kernel}."}, f)
    return out_name

df = collect_all_reports(ROOT)
for kernel in df['kernel'].unique():
    make_kernel_chart(df, kernel)