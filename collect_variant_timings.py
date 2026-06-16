#!/usr/bin/env python3
"""
collect_variant_timings.py

Sweeps through all C++ and DaCe result folders and writes every
variant's timing / status parameters to a single CSV file.

C++ layout:
  <cpp_root>/<tsvc_ver>/<compiler>_<cpu>_<cost_model>/build/
      <kernel>_<prec>_<variant>.o        e.g. s000_d_single.o
      <kernel>_<prec>_<variant>.rpt      e.g. s000_d_single.rpt  (vectorisation report)
      libtsvc_kernels.so / libtsvc_kernels.dylib

DaCe layout:
  <dace_root>/<tsvc_ver>/<compiler>_<cpu>_<cost_model>/build/
      <kernel>_<prec>_<variant>/         e.g. s000_d_single/
          program.sdfgz
          dace_environments.csv
          dace_files.csv
          perf/                          <- timing CSVs/JSON written here at runtime
          map/map_cpp.json
          map/map_py.json
          build/
              libs<kernel>_<prec>_<variant>.dylib   <- present = success
              cmake_configure.sh

Usage:
  python3 collect_variant_timings.py
  python3 collect_variant_timings.py --cpp-root results_cpp --dace-root results_dace --out timings.csv
  python3 collect_variant_timings.py --tsvc-versions tsvc_2 tsvc_2_5
  python3 collect_variant_timings.py --backends cpp
  python3 collect_variant_timings.py --backends dace --cost-models default unlimited
  python3 collect_variant_timings.py --precisions double --variants single
"""

import argparse
import csv
import json
import pathlib
import re
import time

# ── Constants ──────────────────────────────────────────────────────────────────
KNOWN_COMPILERS  = ["clang", "gcc", "icpx", "icc", "nvcc"]
KNOWN_COST_MODELS = ["default", "cheap", "unlimited", "disabled"]
PREC_MAP         = {"d": "double", "f": "float"}
VARIANT_MAP      = {"single": "single", "": "base"}

# Matches both C++ filenames  (s000_d_single.o)  and DaCe folder names  (s000_d_single)
# Kernel names: start with a letter, then letters/digits; may contain underscores
# that are NOT the precision separator — precision is always a lone _d_ or _f_
# followed optionally by _single.
_KERNEL_RE = re.compile(
    r"^(?P<kernel>[a-z][a-z0-9_]*?)_(?P<prec>[df])(?:_(?P<var>single))?(?:\.o)?$"
)

COST_MODELS_DEFAULT   = ["default", "cheap", "unlimited", "disabled"]
TSVC_VERSIONS_DEFAULT = ["tsvc_2", "tsvc_2_5"]
BACKENDS_DEFAULT      = ["cpp", "dace"]
PRECISIONS_DEFAULT    = ["double", "float"]
VARIANTS_DEFAULT      = ["base", "single"]


# ── Parsing helpers ────────────────────────────────────────────────────────────

def _parse_kernel_name(name: str):
    """
    Parse  s000_d_single  or  s000_d_single.o  →  (kernel, precision, variant).
    Returns None if name does not match expected pattern.
    """
    m = _KERNEL_RE.match(name)
    if not m:
        return None
    prec = PREC_MAP.get(m.group("prec"))
    var  = VARIANT_MAP.get(m.group("var") or "")
    if prec is None or var is None:
        return None
    return m.group("kernel"), prec, var


def _split_variant_dir(dirname: str):
    """
    Split  clang_apple_m_series_default  →  (compiler, cpu, cost_model).

    Strategy: match known compiler prefix first, then strip known cost-model
    suffix, leaving the CPU string in the middle.
    """
    compiler = None
    for c in KNOWN_COMPILERS:
        if dirname.startswith(c + "_"):
            compiler = c
            break
    if compiler is None:
        # fallback: first token
        compiler = dirname.split("_")[0]

    rest = dirname[len(compiler) + 1:]   # strip "clang_"

    cost_model = None
    for cm in KNOWN_COST_MODELS:
        if rest.endswith("_" + cm):
            cost_model = cm
            rest = rest[: -(len(cm) + 1)]   # strip "_default"
            break
    if cost_model is None:
        cost_model = rest.split("_")[-1]
        rest = "_".join(rest.split("_")[:-1])

    cpu = rest   # e.g. "apple_m_series"
    return compiler, cpu, cost_model


# ── Per-file readers ───────────────────────────────────────────────────────────

def _read_rpt(rpt_path: pathlib.Path) -> dict:
    """
    Read a per-kernel .rpt vectorisation report.

    The report format is compiler-specific.  We extract:
      - vectorized:  True/False  (whether the loop was reported vectorized)
      - vec_width:   integer width if mentioned  (e.g. 256-bit, width 4)
      - rpt_raw:     first 400 chars of file for debugging
    """
    out = {"rpt_vectorized": None, "rpt_vec_width": None, "rpt_raw": ""}
    if not rpt_path.exists():
        return out
    try:
        text = rpt_path.read_text(errors="replace")
    except OSError:
        return out

    out["rpt_raw"] = text[:400].replace("\n", " ")

    # GCC / Clang style: "vectorized N loops"  or  "loop vectorized"
    if re.search(r"vectorized\s+[1-9]\d*\s+loop|loop\s+vectorized", text, re.I):
        out["rpt_vectorized"] = True
    elif re.search(r"not\s+vectorized|vectorized\s+0\s+loop", text, re.I):
        out["rpt_vectorized"] = False

    # Width hints:  256-bit  /  vf=4  /  vector width = 8
    mw = re.search(r"(\d+)-bit|vf\s*=\s*(\d+)|vector\s+width\s*[=:]\s*(\d+)", text, re.I)
    if mw:
        out["rpt_vec_width"] = next(g for g in mw.groups() if g is not None)

    return out


def _dace_compile_status(kernel_dir: pathlib.Path) -> str:
    """
    success           – shared lib present under build/
    compile_failed    – cmake_configure.sh exists but no lib
    missing_build_dir – build/ subdirectory is absent entirely
    not_attempted     – kernel_dir exists but nothing was written
    """
    build_dir = kernel_dir / "build"
    if not build_dir.is_dir():
        return "missing_build_dir"
    libs = (list(build_dir.glob("libs*.dylib")) +
            list(build_dir.glob("libs*.so")))
    if libs:
        return "success"
    if (build_dir / "cmake_configure.sh").exists():
        return "compile_failed"
    return "not_attempted"


def _dace_perf(kernel_dir: pathlib.Path) -> dict:
    """Read CSV / JSON files from perf/; return flat dict prefixed perf_."""
    timings = {}
    perf_dir = kernel_dir / "perf"
    if not perf_dir.is_dir():
        return timings
    for p in sorted(perf_dir.iterdir()):
        if p.suffix == ".csv":
            try:
                with p.open() as f:
                    for row in csv.DictReader(f):
                        for k, v in row.items():
                            timings[f"perf_{p.stem}_{k}"] = v
                        break
            except Exception:
                pass
        elif p.suffix == ".json":
            try:
                data = json.loads(p.read_text())
                if isinstance(data, dict):
                    for k, v in data.items():
                        if not isinstance(v, (dict, list)):
                            timings[f"perf_{p.stem}_{k}"] = v
            except Exception:
                pass
    return timings


def _dace_map_info(kernel_dir: pathlib.Path) -> dict:
    """Read map/map_cpp.json and map/map_py.json; return flat scalar fields."""
    info = {}
    map_dir = kernel_dir / "map"
    for fname in ("map_cpp.json", "map_py.json"):
        p = map_dir / fname
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text())
            prefix = fname.replace(".json", "") + "_"
            if isinstance(data, dict):
                for k, v in data.items():
                    if not isinstance(v, (dict, list)):
                        info[prefix + k] = v
        except Exception:
            pass
    return info


def _dace_env_info(kernel_dir: pathlib.Path) -> dict:
    """Read first row of dace_environments.csv."""
    env = {}
    p = kernel_dir / "dace_environments.csv"
    if not p.exists():
        return env
    try:
        with p.open() as f:
            for row in csv.DictReader(f):
                for k, v in row.items():
                    env[f"env_{k}"] = v
                break
    except Exception:
        pass
    return env


def _so_mtime(build_dir: pathlib.Path):
    """Return ISO mtime of the shared lib, or None."""
    for pattern in ("libtsvc_kernels.so", "libtsvc_kernels.dylib"):
        p = build_dir / pattern
        if p.exists():
            return time.strftime("%Y-%m-%dT%H:%M:%S",
                                 time.localtime(p.stat().st_mtime))
    return None


# ── Core sweepers ──────────────────────────────────────────────────────────────

def sweep_cpp(cpp_root, tsvc_versions, cost_models, precisions, variants):
    rows = []
    for ver in tsvc_versions:
        ver_dir = cpp_root / ver
        if not ver_dir.is_dir():
            continue
        for cfg_dir in sorted(ver_dir.iterdir()):
            if not cfg_dir.is_dir():
                continue
            compiler, cpu, cost_model = _split_variant_dir(cfg_dir.name)
            if cost_model not in cost_models:
                continue
            build_dir = cfg_dir / "build"
            if not build_dir.is_dir():
                continue

            so_mtime  = _so_mtime(build_dir)
            so_exists = so_mtime is not None

            for obj in sorted(build_dir.glob("*.o")):
                parsed = _parse_kernel_name(obj.name)
                if parsed is None:
                    continue
                kernel, prec, var = parsed
                if prec not in precisions or var not in variants:
                    continue

                rpt_path = obj.with_suffix(".rpt")
                rpt_data = _read_rpt(rpt_path)

                rows.append({
                    "backend":        "cpp",
                    "tsvc_version":   ver,
                    "compiler":       compiler,
                    "cpu":            cpu,
                    "cost_model":     cost_model,
                    "precision":      prec,
                    "variant":        var,
                    "kernel":         kernel,
                    "compile_status": "obj_compiled" if obj.exists() else "missing_obj",
                    "so_link_status": "success" if so_exists else "link_failed",
                    "obj_exists":     obj.exists(),
                    "so_exists":      so_exists,
                    "so_mtime":       so_mtime,
                    "rpt_exists":     rpt_path.exists(),
                    "sdfgz_exists":   "",
                    **rpt_data,
                    "variant_path":   str(build_dir),
                })
    return rows


def sweep_dace(dace_root, tsvc_versions, cost_models, precisions, variants):
    rows = []
    for ver in tsvc_versions:
        ver_dir = dace_root / ver
        if not ver_dir.is_dir():
            continue
        for cfg_dir in sorted(ver_dir.iterdir()):
            if not cfg_dir.is_dir():
                continue
            compiler, cpu, cost_model = _split_variant_dir(cfg_dir.name)
            if cost_model not in cost_models:
                continue
            build_dir = cfg_dir / "build"
            if not build_dir.is_dir():
                continue

            for kernel_dir in sorted(build_dir.iterdir()):
                if not kernel_dir.is_dir():
                    continue
                parsed = _parse_kernel_name(kernel_dir.name)
                if parsed is None:
                    continue
                kernel, prec, var = parsed
                if prec not in precisions or var not in variants:
                    continue

                status = _dace_compile_status(kernel_dir)
                rows.append({
                    "backend":        "dace",
                    "tsvc_version":   ver,
                    "compiler":       compiler,
                    "cpu":            cpu,
                    "cost_model":     cost_model,
                    "precision":      prec,
                    "variant":        var,
                    "kernel":         kernel,
                    "compile_status": status,
                    "so_link_status": status,
                    "obj_exists":     (kernel_dir / "build").is_dir(),
                    "so_exists":      status == "success",
                    "so_mtime":       None,
                    "rpt_exists":     False,
                    "sdfgz_exists":   (kernel_dir / "program.sdfgz").exists(),
                    "rpt_vectorized": None,
                    "rpt_vec_width":  None,
                    "rpt_raw":        "",
                    **_dace_perf(kernel_dir),
                    **_dace_map_info(kernel_dir),
                    **_dace_env_info(kernel_dir),
                    "variant_path":   str(kernel_dir),
                })
    return rows


# ── CSV writer ─────────────────────────────────────────────────────────────────

def write_csv(rows, out_path: pathlib.Path):
    if not rows:
        print("No rows collected — check that your result directories exist.")
        return

    # Core columns always appear first in the CSV regardless of row order
    core = [
        "backend", "tsvc_version", "compiler", "cpu", "cost_model",
        "precision", "variant", "kernel",
        "compile_status", "so_link_status",
        "obj_exists", "so_exists", "so_mtime",
        "rpt_exists", "sdfgz_exists",
        "rpt_vectorized", "rpt_vec_width", "rpt_raw",
        "variant_path",
    ]
    seen  = set(core)
    extra = []
    for row in rows:
        for k in row:
            if k not in seen:
                extra.append(k)
                seen.add(k)

    fieldnames = core + extra
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames,
                           extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows  →  {out_path.resolve()}")


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Sweep C++ and DaCe result folders and emit a timing/status CSV."
    )
    ap.add_argument("--cpp-root",  default="results_cpp",        metavar="DIR")
    ap.add_argument("--dace-root", default="results_dace",       metavar="DIR")
    ap.add_argument("--out",       default="variant_timings.csv", metavar="FILE")
    ap.add_argument("--backends",       nargs="+", default=BACKENDS_DEFAULT,
                    choices=["cpp", "dace"])
    ap.add_argument("--tsvc-versions",  nargs="+", default=TSVC_VERSIONS_DEFAULT,
                    metavar="VER")
    ap.add_argument("--cost-models",    nargs="+", default=COST_MODELS_DEFAULT,
                    metavar="MODEL")
    ap.add_argument("--precisions",     nargs="+", default=PRECISIONS_DEFAULT,
                    choices=["double", "float"])
    ap.add_argument("--variants",       nargs="+", default=VARIANTS_DEFAULT,
                    choices=["base", "single"])
    args = ap.parse_args()

    cpp_root  = pathlib.Path(args.cpp_root)
    dace_root = pathlib.Path(args.dace_root)
    out_path  = pathlib.Path(args.out)
    rows = []

    if "cpp" in args.backends:
        if not cpp_root.exists():
            print(f"WARNING: {cpp_root!r} not found — skipping C++ sweep.")
        else:
            r = sweep_cpp(cpp_root, args.tsvc_versions, args.cost_models,
                          args.precisions, args.variants)
            print(f"C++  sweep: {len(r)} kernel-variants found.")
            rows.extend(r)

    if "dace" in args.backends:
        if not dace_root.exists():
            print(f"WARNING: {dace_root!r} not found — skipping DaCe sweep.")
        else:
            r = sweep_dace(dace_root, args.tsvc_versions, args.cost_models,
                           args.precisions, args.variants)
            print(f"DaCe sweep: {len(r)} kernel-variants found.")
            rows.extend(r)

    write_csv(rows, out_path)


if __name__ == "__main__":
    main()