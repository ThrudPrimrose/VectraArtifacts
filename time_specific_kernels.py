#!/usr/bin/env python3
"""
time_specific_kernels.py — raw execution-time benchmark for a hand-picked
subset of TSVC kernels: CPP (native baseline) vs DaCe, run through each
backend's own internal timer, writing raw per-repetition timings to CSV.

Why "each backend's own timer" matters
---------------------------------------
* CPP side: every ``tsvc_*_microkernels/<kernel>/<kernel>_{d,f}[_single].cpp``
  has a ``std::chrono::high_resolution_clock`` pair baked directly into the
  kernel body by the split/codegen step, reporting elapsed nanoseconds back
  through an ``int64_t*`` out-parameter. Timing it just means calling the
  compiled symbol and reading that pointer back — see
  ``vectra_artifacts.corpus_build.compile_cpp.run_timing_phase``, reused
  here unmodified.

* DaCe side: this script sets ``sdfg.instrument =
  dace.dtypes.InstrumentationType.Timer`` before compiling, which makes
  DaCe itself inject a ``std::chrono`` pair around the whole compiled
  program (see ``dace/codegen/instrumentation/timer.py``) and report the
  duration through DaCe's own instrumentation-report JSON — NOT a
  ``time.perf_counter()`` wrapped around the Python call (which is what
  ``compile_dace.py``'s existing ``--time`` path does, and which also
  includes Python/ctypes marshalling overhead on every call). Reps are run
  back-to-back with ``instrumentation/report_each_invocation`` turned off
  so DaCe accumulates every rep into ONE report, flushed once via
  ``csdfg.finalize()`` and then split back out per-rep — giving a native,
  apples-to-apples counterpart to the CPP side's embedded chrono timer.

Compiler / cost-model / CPU flags for BOTH backends are resolved from the
single canonical ``vectra_artifacts.compilers.get_flags`` /
``configure_dace`` API (no bash env-sourcing, no subprocess — this runs
entirely in-process), so CPP and DaCe are guaranteed to see the exact same
flags for a given (compiler, cost-model, cpu) combination.

Output layout
-------------
Per (precision, compiler, cpu, cost-model) combo, writes into the SAME
``results_cpp/<tsvc_version>/<precision>/<combo>/`` and
``results_dace/<tsvc_version>/<precision>/<combo>/`` layout already used by
only_timing.py — so ``timing_boxplot.py`` / ``timing_violinplot.py`` (this
repo's existing box/violin plotters) work unmodified against it:

    timing_report.csv              summary (median/min/stdev, ...)
    timing_report_raw_timings.csv  ONE ROW PER REPETITION — this is the
                                    "raw timing test" / box-plot input.

It additionally writes a normalized, unit-unified, bare-kernel-named
comparison pair per combo under --out-dir (default
``results_specific/<tsvc_version>/<run-timestamp>/<precision>/<combo>/``):

    combined_raw_timings.csv   kernel,variant,rep,timing_us   (variant: cpp|dace)
    combined_summary.csv       kernel,variant,median_us,min_us,max_us,stdev_us,n

plus one ``run_manifest.txt`` at the --out-dir root recording the CLI args,
host/SLURM identity, and per-combo resolved compiler flags, for provenance.

Examples
--------
# A handful of kernels, default config (clang/unlimited/apple_m_series), 100 runs each
python3 time_specific_kernels.py --kernels s313 s314 s453 vdotr --runs 100

# Same kernels, box-plot-grade sample size, on the cluster (compiler/cpu from the job)
python3 time_specific_kernels.py \\
    --kernels s313 s314 s453 vdotr s352 \\
    --compilers clang gcc --cost-models default unlimited \\
    --cpus arm_grace --precision both --runs 500 --out-dir results_specific/box_run

# CPP only, reusing an existing venv/toolchain already on PATH
python3 time_specific_kernels.py --kernels s313 --no-dace --runs 1000

See also: cluster/time_specific_kernels.sbatch.sh for a SLURM submission
template, and timing_violinplot.py to turn the raw CSVs into real
(non-synthetic) box/violin plots.
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import pathlib
import platform
import re
import socket
import statistics
import sys
import time as _time
from collections import defaultdict
from typing import Optional

REPO_ROOT = pathlib.Path(__file__).resolve().parent
os.chdir(REPO_ROOT)  # everything below assumes cwd == repo root (cluster jobs may cd elsewhere)
sys.path.insert(0, str(REPO_ROOT / "src"))


# ── Valid choices ───────────────────────────────────────────────────────────
ALL_COMPILERS   = ("clang", "gcc", "icpx")
ALL_COST_MODELS = ("default", "cheap", "unlimited", "disabled")
ALL_CPUS        = (
    "amd_epyc", "amd_epyc_genoa", "apple_m_series",
    "arm_grace", "fugaku_a64fx", "ibm_power", "intel_xeon",
)
ALL_PRECISIONS  = ("double", "float", "both")

TSVC_VERSION_CONFIG = {
    "tsvc_2": {
        "cpp_kernels_dir":  "tsvc_2/tsvc_cpp_microkernels",
        "dace_kernels_dir": "tsvc_2/tsvc_dace_microkernels",
    },
    "tsvc_2_5": {
        "cpp_kernels_dir":  "tsvc_2_5/tsvc_2_5_cpp_microkernels",
        "dace_kernels_dir": "tsvc_2_5/tsvc_2_5_dace_microkernels",
    },
}

# Glob patterns with '*' standing in for the kernel base name — swap it in
# with str.replace() to get the exact filename for one kernel.
_PRECISION_PATTERNS = {
    ("double", "tsvc_2"):   ("*_d_single.cpp", "*_d_single.py"),
    ("float",  "tsvc_2"):   ("*_f_single.cpp", "*_f_single.py"),
    ("double", "tsvc_2_5"): ("*_d.cpp",        "*_d.py"),
    ("float",  "tsvc_2_5"): ("*_f.cpp",        "*_f.py"),
}

_KERNEL_SUFFIX_RE = re.compile(r"_(d|f)(_single)?$")


def _bare_kernel(name: str) -> str:
    """Strip a trailing _d / _f / _d_single / _f_single precision suffix."""
    return _KERNEL_SUFFIX_RE.sub("", name)


def _kernel_source_path(root: pathlib.Path, kernel: str, pattern: str) -> Optional[pathlib.Path]:
    exact_name = pattern.replace("*", kernel)
    matches = sorted(root.rglob(exact_name))
    return matches[0] if matches else None


def _read_csv_body(path: pathlib.Path) -> tuple[Optional[str], list[list[str]]]:
    """Return (header_line, data_rows) for a CSV, or (None, []) if it doesn't exist yet."""
    if not path.exists():
        return None, []
    lines = path.read_text().splitlines()
    if not lines:
        return None, []
    return lines[0], [line.split(",") for line in lines[1:] if line.strip()]


def _merge_kernel_rows(
    kept_rows: list[list[str]], new_rows: list[list[str]], replace_kernels: set[str]
) -> list[list[str]]:
    """kept_rows minus anything for a kernel we just recomputed, plus new_rows — stable-sorted
    by kernel (first field) so each kernel's own row order is preserved within its group."""
    kept = [r for r in kept_rows if r and r[0] not in replace_kernels]
    merged = kept + new_rows
    merged.sort(key=lambda r: r[0])
    return merged


def _merge_write_csv(path: pathlib.Path, header: str, new_rows: list[tuple], replace_kernels: set[str]) -> None:
    """
    Write `new_rows` (each row's first field is a kernel name) to `path`,
    preserving any pre-existing rows for OTHER kernels already there. Plain
    write_text() would silently wipe out, e.g., a prior baseline run's rows
    the next time a --dace-variant run (or any run touching a different
    kernel subset) writes into the same results dir.
    """
    _, old_rows = _read_csv_body(path)
    merged = _merge_kernel_rows(old_rows, [[str(x) for x in row] for row in new_rows], replace_kernels)
    path.write_text("\n".join([header] + [",".join(r) for r in merged]) + "\n")


# ── SLURM / cluster helpers ──────────────────────────────────────────────────
def _resolve_shard(args) -> tuple[int, int]:
    shard_id   = args.shard_id
    num_shards = args.num_shards
    if shard_id is None:
        shard_id = int(os.environ.get("SLURM_PROCID", 0))
    if num_shards is None:
        num_shards = int(os.environ.get("SLURM_NTASKS", 1))
    if num_shards < 1:
        raise ValueError(f"--num-shards must be >= 1, got {num_shards}")
    if not (0 <= shard_id < num_shards):
        raise ValueError(f"--shard-id {shard_id} out of range for --num-shards {num_shards}")
    return shard_id, num_shards


def _host_info_lines() -> list[str]:
    return [
        f"host          : {socket.gethostname()}",
        f"platform      : {platform.platform()}",
        f"python        : {sys.version.split()[0]}",
        f"cpu_count     : {os.cpu_count()}",
        f"SLURM_JOB_ID  : {os.environ.get('SLURM_JOB_ID', '-')}",
        f"SLURM_NODELIST: {os.environ.get('SLURM_NODELIST', '-')}",
        f"SLURM_PROCID  : {os.environ.get('SLURM_PROCID', '-')}",
        f"SLURM_NTASKS  : {os.environ.get('SLURM_NTASKS', '-')}",
    ]


# ── DaCe timing worker — runs through DaCe's OWN Timer instrumentation ──────
def _dace_timer_worker(args_tuple):
    """
    Compile one DaCe kernel and time it via DaCe's own
    ``dace.dtypes.InstrumentationType.Timer`` instrumentation — a
    std::chrono pair DaCe injects into the generated C++ around the whole
    program, harvested from DaCe's own instrumentation report. This is
    deliberately NOT a ``time.perf_counter()`` wrapper around the Python
    call.

    ``instrumentation/report_each_invocation`` is turned off so ALL calls
    (1 warm-up + `reps` timed) accumulate into a single report, flushed
    once via ``csdfg.finalize()`` — avoiding the millisecond-resolution
    report-filename collisions that per-invocation report files would hit
    at microkernel speeds.

    Runs inside an isolated (forked) subprocess via Pool.apply_async so a
    hang or crash in DaCe / the generated code can't take the whole run
    down; the caller applies its own timeout.

    If ``variant_cpp`` is given, an initial normal compile runs first (DaCe
    needs the auto-generated CMakeLists.txt / stub headers alongside the
    kernel .cpp — a hand-edited .cpp alone isn't a buildable tree), then
    that compile's generated ``src/cpu/*.cpp`` is overwritten with
    ``variant_cpp``'s contents and ``sdfg.regenerate_code`` is set to
    False before recompiling — this is the ONLY correct way to get DaCe to
    rebuild from hand-edited generated code: ``compiler:use_cache`` looks
    tempting but is wrong here, since (per dace/sdfg/sdfg.py's
    ``SDFG.compile()``) it just reloads the existing .so unchanged when one
    is already present, without even looking at the .cpp on disk.
    Overridden kernels are reported back under ``"<kernel>__<variant
    stem>"`` (not the bare kernel name) so a baseline run and a variant run
    pointed at the same results dir accumulate as distinct, directly
    comparable rows instead of one silently overwriting the other.

    Returns (reported_name, "ok", raw_timings_us) on success, or
    (kernel, None, error_message) on failure.
    """
    py_file, kernel, kdir, len_1d, is_float, reps, variant_cpp = args_tuple

    import importlib.util
    import pathlib as _pl
    import time as _tm

    import dace
    import dace.config
    import dace.dtypes
    from vectra_artifacts.corpus_build.compile_dace import _build_dace_kwargs, _make_array_pool

    _t0 = _tm.perf_counter()
    def _log(msg):
        # Phase-by-phase progress so a stall shows WHERE it's stuck (pool
        # build vs. compile vs. variant recompile vs. reps) instead of just
        # a bare "timed out after Ns" with no idea which phase ate the time.
        # This runs inside a forked worker but stdout is inherited from the
        # parent, so it lands in the same job log as everything else.
        print(f"    [dace-worker] {kernel} +{_tm.perf_counter() - _t0:6.1f}s  {msg}", flush=True)

    dace.config.Config.set("compiler", "allow_view_arguments", value=True)

    # Local dev convenience (macOS Homebrew OpenMP); harmless no-op on Linux clusters.
    homebrew_omp = _pl.Path("/opt/homebrew/opt/libomp")
    if homebrew_omp.exists():
        inc, lib = str(homebrew_omp / "include"), str(homebrew_omp / "lib")
        existing = dace.config.Config.get("compiler", "cpu", "args") or ""
        if inc not in existing:
            dace.config.Config.set("compiler", "cpu", "args", value=f"{existing} -I{inc} -L{lib} -lomp")

    # Accumulate every call's Timer completion into ONE report, flushed at finalize().
    dace.config.Config.set("instrumentation", "report_each_invocation", value=False)

    try:
        spec = importlib.util.spec_from_file_location(kernel, str(py_file))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        prog = next(
            (getattr(mod, a) for a in dir(mod)
             if not a.startswith("_") and hasattr(getattr(mod, a, None), "to_sdfg")),
            None,
        )
        if prog is None:
            return kernel, None, "no @dace.program found"
        sdfg = prog.to_sdfg()
        _log("to_sdfg() done")
    except Exception as exc:
        return kernel, None, f"load/to_sdfg failed: {exc}"

    kdir.mkdir(parents=True, exist_ok=True)
    sdfg.build_folder = str(kdir / "build")
    sdfg.instrument = dace.dtypes.InstrumentationType.Timer

    pool = _make_array_pool(len_1d, is_float)
    _log(f"array pool built (len_1d={len_1d})")
    kwargs, missing = _build_dace_kwargs(sdfg, pool)
    if kwargs is None:
        return kernel, None, f"unresolved args: {missing}"

    try:
        # When a variant override follows, this compile exists ONLY to
        # produce a buildable tree to overwrite -- don't load the .so into
        # the process (return_program_handle=False). Loading it here and
        # then loading a second .so at the same path after the variant
        # recompile hits DaCe's "already loaded, renaming file" path,
        # which -- at least on Lustre-backed scratch, reproduced on daint
        # at len_1d=2**26 -- can hand back a renamed copy missing its
        # __dace_init_* symbol (a write/copy race), failing the whole run.
        # Skipping the load here means there's nothing to collide with.
        csdfg = sdfg.compile(return_program_handle=(variant_cpp is None))
        _log("baseline sdfg.compile() done")
    except Exception as exc:
        return kernel, None, f"compile failed: {exc}"

    reported_name = kernel
    if variant_cpp is not None:
        # DaCe writes one .cpp PER CODE OBJECT, and a kernel with a nested
        # SDFG (e.g. a reduction) gets more than one file under src/cpu/ --
        # a "grab whichever file is most deeply nested" heuristic can pick
        # a nested-SDFG file instead of the actual top-level program file
        # (reproduced on daint: it silently overwrote a nested file, so the
        # real one it then tried to load was untouched, and worse, DaCe's
        # __dace_init_<sdfg.name> symbol lookup uses THIS sdfg.name, which
        # didn't match what got written). The top-level file is
        # unambiguous: it's always named exactly f"{sdfg.name}.cpp" -- the
        # same name the __dace_init_* linker symbol is keyed on -- so target
        # that path directly instead of guessing among multiple candidates.
        target_cpp = _pl.Path(sdfg.build_folder) / "src" / "cpu" / f"{sdfg.name}.cpp"
        if not target_cpp.is_file():
            return kernel, None, f"variant override requested but expected generated source not found: {target_cpp}"
        _log(f"found generated source to override: {target_cpp}")

        try:
            target_cpp.write_text(_pl.Path(variant_cpp).read_text())
        except Exception as exc:
            return kernel, None, f"failed writing variant source {variant_cpp} -> {target_cpp}: {exc}"

        sdfg.regenerate_code = False   # keep the edited .cpp; just rebuild+relink from it
        try:
            csdfg = sdfg.compile()
            _log("variant sdfg.compile() (rebuild-only) done")
        except Exception as exc:
            return kernel, None, f"variant recompile failed: {exc}"

        reported_name = f"{kernel}__{_pl.Path(variant_cpp).stem}"

    try:
        sdfg.clear_instrumentation_reports()
    except Exception:
        pass

    try:
        csdfg(**kwargs)              # warm-up — its Timer event is discarded below
        _log("warm-up call done")
        for i in range(reps):
            csdfg(**kwargs)
            if reps >= 20 and (i + 1) % max(1, reps // 5) == 0:
                _log(f"reps: {i + 1}/{reps}")
        _log(f"all {reps} reps done")
        csdfg.finalize()             # flushes the accumulated Timer report to disk
        _log("csdfg.finalize() done")
    except Exception as exc:
        return kernel, None, f"run failed: {exc}"

    report = sdfg.get_latest_report()
    if report is None:
        return kernel, None, "no instrumentation report written"

    target_name = f"SDFG {sdfg.name}"
    events = sorted(
        (e for e in report.events if getattr(e, "name", None) == target_name),
        key=lambda e: e.timestamp,
    )

    if len(events) != reps + 1:
        return kernel, None, (
            f"expected {reps + 1} Timer events (1 warm-up + {reps} reps), got {len(events)} "
            "— report_each_invocation / report harvesting mismatch"
        )

    timings_us = [e.duration for e in events[1:]]  # drop the warm-up event
    return reported_name, "ok", timings_us


def run_dace_subset(
    kernels: list[str],
    dace_root: pathlib.Path,
    is_float: bool,
    flag_set,
    build_dir: pathlib.Path,
    out_dir: pathlib.Path,
    pattern_dace: str,
    reps: int,
    len_1d: int,
    kernel_timeout: int,
    variants: Optional[dict[str, str]] = None,
) -> tuple[Optional[pathlib.Path], list[str], dict[str, str]]:
    from vectra_artifacts.compilers import configure_dace
    configure_dace(flag_set)
    cxx_override = os.environ.get("CXX")
    if cxx_override:
        import dace.config
        dace.config.Config.set("compiler", "cpu", "executable", value=cxx_override)

    variants = variants or {}
    missing: list[str] = []
    work_items = []
    for k in kernels:
        src = _kernel_source_path(dace_root, k, pattern_dace)
        if src is None:
            missing.append(k)
            continue
        work_items.append((src, k, build_dir / k, len_1d, is_float, reps, variants.get(k)))
    if missing:
        print(f"  [dace] WARNING: no DaCe source for: {', '.join(missing)}", file=sys.stderr)

    rows: list[tuple] = []
    raw_rows: list[tuple] = []
    failures: dict[str, str] = {}

    if work_items:
        mp_ctx = multiprocessing.get_context("fork" if sys.platform != "win32" else "spawn")
        pool = mp_ctx.Pool(processes=1)
        try:
            for item in work_items:
                kernel = item[1]
                variant_tag = f" [variant: {pathlib.Path(item[6]).name}]" if item[6] else ""
                print(f"  [dace] timing {kernel}{variant_tag} ...", end=" ", flush=True)
                async_result = pool.apply_async(_dace_timer_worker, (item,))
                try:
                    k_r, status, payload = async_result.get(timeout=kernel_timeout)
                    if status != "ok":
                        print(f"SKIP — {payload}", flush=True)
                        failures[kernel] = str(payload)
                    else:
                        timings_us = payload
                        med, mn, mx = statistics.median(timings_us), min(timings_us), max(timings_us)
                        sd = statistics.stdev(timings_us) if len(timings_us) > 1 else 0.0
                        print(f"ok  median={med:.1f}µs  min={mn:.1f}µs  -> reported as '{k_r}'", flush=True)
                        rows.append((k_r, med, mn, mx, sd, len(timings_us)))
                        for rep_idx, t in enumerate(timings_us):
                            raw_rows.append((k_r, rep_idx, t))
                except multiprocessing.TimeoutError:
                    print(f"SKIP — timed out after {kernel_timeout}s", flush=True)
                    failures[kernel] = f"timed out after {kernel_timeout}s"
                    pool.terminate(); pool.join(); pool = mp_ctx.Pool(processes=1)
                except Exception as exc:
                    print(f"SKIP — worker error: {exc}", flush=True)
                    failures[kernel] = str(exc)
                    pool.terminate(); pool.join(); pool = mp_ctx.Pool(processes=1)
        finally:
            pool.terminate()
            pool.join()

    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "timing_report.csv"
    raw_csv = out_dir / "timing_report_raw_timings.csv"

    reported_kernels = {r[0] for r in rows}
    _merge_write_csv(
        out_csv, "kernel,median_us,min_us,max_us,stdev_us,reps",
        [(k, f"{med:.3f}", f"{mn:.3f}", f"{mx:.3f}", f"{sd:.3f}", n) for k, med, mn, mx, sd, n in rows],
        replace_kernels=reported_kernels,
    )
    _merge_write_csv(
        raw_csv, "kernel,rep,timing_us",
        [(k, rep_idx, f"{t:.3f}") for k, rep_idx, t in raw_rows],
        replace_kernels=reported_kernels,
    )

    print(f"  [dace] {len(rows)} kernel(s) timed, {len(failures)} failed/skipped -> {out_csv}")
    return raw_csv, missing, failures


# ── CPP timing — reuses the existing embedded-chrono-timer .so pipeline ─────
def run_cpp_subset(
    kernels: list[str],
    cpp_root: pathlib.Path,
    flag_set,
    build_dir: pathlib.Path,
    out_dir: pathlib.Path,
    pattern_cpp: str,
    reps: int,
    len_1d: int,
    kernel_timeout: int,
    force: bool,
) -> tuple[Optional[pathlib.Path], list[str]]:
    from vectra_artifacts.corpus_build import compile_cpp

    # Point compile_cpp's module-level compiler config at THIS combo's
    # resolved flags (compile_object/link_library read these as globals at
    # call time, so mutating them here is enough — no subprocess needed).
    compile_cpp.CXX           = os.environ.get("CXX") or flag_set.compiler.executable()
    compile_cpp.COMPILE_FLAGS = list(flag_set.compile_flags)
    compile_cpp.LINK_FLAGS    = list(flag_set.link_flags)

    missing: list[str] = []
    src_files: list[pathlib.Path] = []
    for k in kernels:
        src = _kernel_source_path(cpp_root, k, pattern_cpp)
        if src is None:
            missing.append(k)
        else:
            src_files.append(src)
    if missing:
        print(f"  [cpp] WARNING: no C++ source for: {', '.join(missing)}", file=sys.stderr)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "timing_report.csv"
    raw_csv = out_dir / "timing_report_raw_timings.csv"

    if not src_files:
        out_csv.write_text("kernel,median_ns,min_ns,stdev_ns,vectorized,vec_count,missed_count,remark_vectorized,remark_mismatch\n")
        raw_csv.write_text("kernel,rep,timing_ns\n")
        return raw_csv, missing

    build_dir.mkdir(parents=True, exist_ok=True)
    objects = [compile_cpp.compile_object(src, build_dir, force=force) for src in src_files]
    so = compile_cpp.link_library(objects, build_dir, "libtsvc_subset.so")

    all_sigs = compile_cpp._load_signatures(cpp_root, so)
    if all_sigs is None:
        out_csv.write_text("kernel,median_ns,min_ns,stdev_ns,vectorized,vec_count,missed_count,remark_vectorized,remark_mismatch\n")
        raw_csv.write_text("kernel,rep,timing_ns\n")
        return raw_csv, missing + ["<tsvc_bindings.py SIGNATURES not found>"]

    wanted = [k for k in kernels if k not in missing]
    sigs = {k: v for k, v in all_sigs.items() if k in wanted}
    unbound = sorted(set(wanted) - set(sigs))
    if unbound:
        print(f"  [cpp] WARNING: no SIGNATURES entry for: {', '.join(unbound)}", file=sys.stderr)

    # run_timing_phase() itself does a plain overwrite of out_csv/raw_csv (it
    # has no notion of "kernels other runs already wrote here") — snapshot
    # what's there first and re-merge afterward so a prior run's kernels
    # (e.g. a different --kernels subset from an earlier invocation) survive.
    prev_summary_header, prev_summary_rows = _read_csv_body(out_csv)
    prev_raw_header, prev_raw_rows = _read_csv_body(raw_csv)

    compile_cpp.run_timing_phase(
        so_path=so,
        signatures=sigs,
        out_csv=out_csv,
        pattern=pattern_cpp,
        reps=reps,
        len_1d=len_1d,
        build_dir=None,          # skip vec-report lookup — not this script's concern
        kernel_timeout=kernel_timeout,
        raw_csv=raw_csv,
    )

    new_summary_header, new_summary_rows = _read_csv_body(out_csv)
    new_raw_header, new_raw_rows = _read_csv_body(raw_csv)
    just_computed = {r[0] for r in new_summary_rows} if new_summary_rows else set(sigs)

    summary_header = new_summary_header or prev_summary_header or \
        "kernel,median_ns,min_ns,stdev_ns,vectorized,vec_count,missed_count,remark_vectorized,remark_mismatch"
    merged_summary = _merge_kernel_rows(prev_summary_rows, new_summary_rows, just_computed)
    out_csv.write_text("\n".join([summary_header] + [",".join(r) for r in merged_summary]) + "\n")

    raw_header = new_raw_header or prev_raw_header or "kernel,rep,timing_ns"
    merged_raw = _merge_kernel_rows(prev_raw_rows, new_raw_rows, just_computed)
    raw_csv.write_text("\n".join([raw_header] + [",".join(r) for r in merged_raw]) + "\n")

    return raw_csv, missing + unbound


# ── Combined, normalized comparison CSV (bare kernel name, unified µs) ──────
def _read_raw_csv(path: Optional[pathlib.Path], to_us: float) -> list[tuple[str, int, float]]:
    if path is None or not path.exists():
        return []
    rows = []
    with path.open() as fh:
        next(fh, None)  # header
        for line in fh:
            line = line.strip()
            if not line:
                continue
            kernel, rep, val = line.split(",")
            rows.append((_bare_kernel(kernel), int(rep), float(val) * to_us))
    return rows


def write_combined(
    cpp_raw_csv: Optional[pathlib.Path],
    dace_raw_csv: Optional[pathlib.Path],
    out_dir: pathlib.Path,
) -> pathlib.Path:
    cpp_rows  = _read_raw_csv(cpp_raw_csv, to_us=1 / 1000)   # ns -> us
    dace_rows = _read_raw_csv(dace_raw_csv, to_us=1.0)       # already us

    out_dir.mkdir(parents=True, exist_ok=True)

    raw_lines = ["kernel,variant,rep,timing_us"]
    for kernel, rep, us in cpp_rows:
        raw_lines.append(f"{kernel},cpp,{rep},{us:.3f}")
    for kernel, rep, us in dace_rows:
        raw_lines.append(f"{kernel},dace,{rep},{us:.3f}")
    (out_dir / "combined_raw_timings.csv").write_text("\n".join(raw_lines) + "\n")

    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for kernel, _rep, us in cpp_rows:
        groups[(kernel, "cpp")].append(us)
    for kernel, _rep, us in dace_rows:
        groups[(kernel, "dace")].append(us)

    summary_lines = ["kernel,variant,median_us,min_us,max_us,stdev_us,n"]
    for (kernel, variant), vals in sorted(groups.items()):
        med, mn, mx = statistics.median(vals), min(vals), max(vals)
        sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
        summary_lines.append(f"{kernel},{variant},{med:.3f},{mn:.3f},{mx:.3f},{sd:.3f},{len(vals)}")
    (out_dir / "combined_summary.csv").write_text("\n".join(summary_lines) + "\n")

    return out_dir / "combined_raw_timings.csv"


# ── CLI ───────────────────────────────────────────────────────────────────────
def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Raw execution-time benchmark (CPP baseline vs DaCe) for a hand-picked subset of TSVC kernels.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument(
        "--kernels", nargs="+", required=True, metavar="KERNEL",
        help="TSVC kernel base names to time, e.g. s313 s314 s453 vdotr (must match a folder "
             "under tsvc_*_microkernels/).",
    )
    ap.add_argument("--tsvc-version", default="tsvc_2", choices=list(TSVC_VERSION_CONFIG), metavar="VERSION")
    ap.add_argument("--precision", default="double", choices=ALL_PRECISIONS,
                     help="'both' times double then float. (default: double)")
    ap.add_argument("--compilers", nargs="+", default=["clang"], choices=ALL_COMPILERS, metavar="COMPILER")
    ap.add_argument("--cost-models", nargs="+", default=["unlimited"], choices=ALL_COST_MODELS, metavar="MODEL")
    ap.add_argument("--cpus", nargs="+", default=["apple_m_series"], choices=ALL_CPUS, metavar="CPU")
    ap.add_argument("--math", action="store_true",
                     help="Enable -ffast-math-family flags via get_flags(math=True). NOTE: currently a "
                          "no-op — vectra_artifacts.compilers.flags._MATH_FLAGS is an empty stub for every "
                          "compiler. Use --extra-cxxflags for a specific flag like -funsafe-math-optimizations "
                          "until that's populated.")
    ap.add_argument("--extra-cxxflags", default="", metavar="FLAGS",
                     help="Space-separated extra compile flags appended for BOTH backends (CPP compile_object "
                          "and DaCe's compiler:cpu:args), e.g. --extra-cxxflags '-funsafe-math-optimizations'.")
    ap.add_argument("--cxx", default=None, metavar="PATH",
                     help="Override the compiler executable for BOTH backends (else $CXX or the canonical default).")
    ap.add_argument(
        "--dace-variant", action="append", default=None, metavar="KERNEL=PATH", dest="dace_variants",
        help="Repeatable. For KERNEL, after the normal DaCe compile, overwrite its generated "
             "src/cpu/*.cpp with the file at PATH (e.g. a hand-edited copy from tsvc_2_adaptations/) "
             "and rebuild WITHOUT regenerating codegen, then time that. Results are reported under "
             "'KERNEL__<PATH stem>' so a baseline run and a variant run into the same results dir "
             "don't overwrite each other. DaCe-side only; the CPP baseline is untouched. "
             "e.g. --dace-variant s313=tsvc_2_adaptations/s313_variants/Working_S313.cpp",
    )

    ap.add_argument("--runs", "--reps", type=int, default=100, metavar="N", dest="reps",
                     help="Repetitions per kernel per backend — this is your box-plot sample size. (default: 100)")
    ap.add_argument("--len-1d", type=int, default=1024, metavar="N", dest="len_1d")
    ap.add_argument("--kernel-timeout", type=int, default=120, metavar="SEC", dest="kernel_timeout")

    ap.add_argument("--results-cpp",  default=None, metavar="DIR",
                     help="Root for the CPP results tree (default: results_cpp/<tsvc-version>) — "
                          "same layout only_timing.py / timing_violinplot.py use.")
    ap.add_argument("--results-dace", default=None, metavar="DIR",
                     help="Root for the DaCe results tree (default: results_dace/<tsvc-version>).")
    ap.add_argument("--out-dir", default=None, metavar="DIR",
                     help="Root for the normalized combined CSVs + run manifest "
                          "(default: results_specific/<tsvc-version>/<run-timestamp>).")
    ap.add_argument("--build-dir", default=None, metavar="DIR",
                     help="Root for compile artifacts (default: .tsvc_build/subset and .dace_build/subset — "
                          "already gitignored).")

    ap.add_argument("--no-cpp",  action="store_true", help="Skip the CPP baseline.")
    ap.add_argument("--no-dace", action="store_true", help="Skip DaCe.")
    ap.add_argument("--force", action="store_true", help="Force CPP object recompilation.")

    ap.add_argument("--shard-id", type=int, default=None, metavar="N",
                     help="0-indexed shard this process handles (over the combo list). Defaults to $SLURM_PROCID.")
    ap.add_argument("--num-shards", type=int, default=None, metavar="K",
                     help="Total number of shards. Defaults to $SLURM_NTASKS (1 = no sharding).")

    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    from vectra_artifacts.compilers import Compiler, CostModel, get_flags

    if args.cxx:
        os.environ["CXX"] = args.cxx

    dace_variants: dict[str, str] = {}
    for spec in (args.dace_variants or []):
        if "=" not in spec:
            print(f"ERROR: --dace-variant expects KERNEL=PATH, got: {spec!r}", file=sys.stderr)
            return 1
        k, _, p = spec.partition("=")
        k, p = k.strip(), p.strip()
        if k not in args.kernels:
            print(f"WARNING: --dace-variant {spec!r} names a kernel not in --kernels ({args.kernels}); ignoring", file=sys.stderr)
            continue
        if not pathlib.Path(p).is_file():
            print(f"ERROR: --dace-variant {spec!r}: no such file: {p}", file=sys.stderr)
            return 1
        dace_variants[k] = p

    vcfg      = TSVC_VERSION_CONFIG[args.tsvc_version]
    cpp_root  = pathlib.Path(vcfg["cpp_kernels_dir"]).resolve()
    dace_root = pathlib.Path(vcfg["dace_kernels_dir"]).resolve()

    precisions = ["double", "float"] if args.precision == "both" else [args.precision]

    results_cpp_root  = pathlib.Path(args.results_cpp  or f"results_cpp/{args.tsvc_version}")
    results_dace_root = pathlib.Path(args.results_dace or f"results_dace/{args.tsvc_version}")
    run_stamp = _time.strftime("%Y%m%dT%H%M%S")
    out_root  = pathlib.Path(args.out_dir or f"results_specific/{args.tsvc_version}/{run_stamp}")
    build_root = pathlib.Path(args.build_dir) if args.build_dir else None
    cpp_build_root  = (build_root / "cpp")  if build_root else pathlib.Path(f".tsvc_build/subset/{args.tsvc_version}")
    dace_build_root = (build_root / "dace") if build_root else pathlib.Path(f".dace_build/subset/{args.tsvc_version}")

    combos = [
        (compiler, cost_model, cpu)
        for compiler   in args.compilers
        for cost_model in args.cost_models
        for cpu        in args.cpus
    ]
    shard_id, num_shards = _resolve_shard(args)
    my_combos = combos[shard_id::num_shards]

    manifest: list[str] = [
        f"time_specific_kernels.py run — {run_stamp}",
        *_host_info_lines(),
        f"tsvc_version  : {args.tsvc_version}",
        f"kernels       : {' '.join(args.kernels)}",
        f"precisions    : {precisions}",
        f"compilers     : {args.compilers}",
        f"cost_models   : {args.cost_models}",
        f"cpus          : {args.cpus}",
        f"math          : {args.math}",
        f"extra cxxflags: {args.extra_cxxflags or '(none)'}",
        f"runs (reps)   : {args.reps}",
        f"len_1d        : {args.len_1d}",
        f"kernel_timeout: {args.kernel_timeout}s",
        f"shard         : {shard_id}/{num_shards} -> {len(my_combos)}/{len(combos)} combo(s) assigned",
        f"skip cpp      : {args.no_cpp}  |  skip dace: {args.no_dace}",
        f"dace variants : {dace_variants if dace_variants else '(none — all baseline)'}",
        "",
    ]

    print("\n".join(manifest[:-1]))
    print(f"results_cpp   : {results_cpp_root}")
    print(f"results_dace  : {results_dace_root}")
    print(f"combined out  : {out_root}")

    for precision in precisions:
        is_float = precision == "float"
        pattern_cpp, pattern_dace = _PRECISION_PATTERNS[(precision, args.tsvc_version)]

        for compiler, cost_model, cpu in my_combos:
            combo_name = f"{compiler}_{cpu}_{cost_model}"
            print(f"\n=== [shard {shard_id}/{num_shards}] [{precision}] {combo_name} ===")

            flag_set = get_flags(
                Compiler(compiler), CostModel(cost_model), math=args.math, cpu=cpu,
                extra=args.extra_cxxflags.split(),
            )
            manifest.append(
                f"[{precision}/{combo_name}] cxx={flag_set.compiler.executable()} "
                f"compile_flags={' '.join(flag_set.compile_flags)}"
            )

            cpp_raw = dace_raw = None
            cpp_missing: list[str] = []
            dace_missing: list[str] = []
            dace_failures: dict[str, str] = {}

            if not args.no_cpp:
                cpp_raw, cpp_missing = run_cpp_subset(
                    kernels=args.kernels,
                    cpp_root=cpp_root,
                    flag_set=flag_set,
                    build_dir=cpp_build_root / precision / combo_name,
                    out_dir=results_cpp_root / precision / combo_name,
                    pattern_cpp=pattern_cpp,
                    reps=args.reps,
                    len_1d=args.len_1d,
                    kernel_timeout=args.kernel_timeout,
                    force=args.force,
                )

            if not args.no_dace:
                dace_raw, dace_missing, dace_failures = run_dace_subset(
                    kernels=args.kernels,
                    dace_root=dace_root,
                    is_float=is_float,
                    flag_set=flag_set,
                    build_dir=dace_build_root / precision / combo_name,
                    out_dir=results_dace_root / precision / combo_name,
                    pattern_dace=pattern_dace,
                    reps=args.reps,
                    len_1d=args.len_1d,
                    kernel_timeout=args.kernel_timeout,
                    variants=dace_variants,
                )

            combined_dir = out_root / precision / combo_name
            combined_path = write_combined(cpp_raw, dace_raw, combined_dir)
            print(f"  combined -> {combined_path}")

            if cpp_missing:
                manifest.append(f"    cpp missing/unbound : {', '.join(cpp_missing)}")
            if dace_missing:
                manifest.append(f"    dace missing source : {', '.join(dace_missing)}")
            if dace_failures:
                for k, msg in dace_failures.items():
                    manifest.append(f"    dace FAILED {k}: {msg}")

    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "run_manifest.txt").write_text("\n".join(manifest) + "\n")
    print(f"\nDone. Manifest -> {out_root / 'run_manifest.txt'}")


if __name__ == "__main__":
    main()
