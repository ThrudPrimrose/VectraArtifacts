"""Regenerate, compile, check and time every CloudSC variant, DaCe vs original Fortran.

Per variant, end to end:

  1. regenerate the SDFG                    (regen_sdfgs.regen -- the generator, imported)
  2. compile the DaCe C++ from that SDFG    (sdfg.compile)
  3. compile/load the Fortran reference     (<variant>_w_timer.f90 via ctypes)
  4. run the NumPy oracle                   (<variant>_numpy.py)
  5. check DaCe-vs-NumPy and Fortran-vs-NumPy INDEPENDENTLY (native.compare)
  6. time both lanes and report

NumPy is the oracle for *every* lane. The DaCe SDFG is generated from the same Fortran
the reference lane runs, so "DaCe agrees with Fortran" would be satisfied by a faithful
translation of a wrong kernel; only an independent implementation catches that.

TIMING -- both lanes report MICROSECONDS, and neither is scaled by hand:

  Fortran   the kernel's own ``TIMER`` out-argument. ``fortran_timer_to_us`` reads the
            scale factor straight out of each .f90 rather than trusting a constant, so a
            variant that scaled differently would be normalised (and announced) instead of
            silently reported 1000x off. The kernel also *prints* a nanosecond figure to
            stdout; that is a red herring, nothing reads it.
  DaCe      ``sdfg.instrument = InstrumentationType.Timer`` and the resulting
            InstrumentationReport. Not a Python wall-clock wrapper.
            Scope: the whole top-level SDFG -- ``on_sdfg_begin``/``on_sdfg_end`` bracket the
            generated ``__program_<name>_internal`` body, so it covers every state plus
            top-level transient alloc/dealloc, but excludes ``__dace_init``/``__dace_exit``
            and all Python-side argument marshalling. The Fortran ``system_clock`` calls
            bracket the subroutine body, which is the comparable region.
            NOTE ``InstrumentationReport.durations`` is milliseconds (report.py divides the
            raw event by 1000); ``DurationEvent.duration`` is the raw microseconds. This
            script reads the events, never the durations dict.

Both lanes are cross-checked against a wall clock: instrumented time can never exceed wall
time, and a 1000x unit slip in either direction breaks one of those bounds loudly.

Run under pyenv py13 with the FaCe branch on PYTHONPATH (see run_all.sh):

    PYTHONPATH=/home/primrose/Work/d-face:/home/primrose/Work/dace-fortran \
        python bench_variants.py [--only <variant>] [--reps N] [--frontend ...]
"""
import argparse
import importlib.util
import os
import re
import shutil
import statistics
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "harness"))

import regen_sdfgs  # noqa: E402  (also installs the mpi4py stub, before dace is imported)
import native  # noqa: E402

# Safe to import ahead of the mpi4py-stub/dace ordering above: configure_dace() only
# imports dace.config lazily, inside its own body, so nothing here touches dace at
# import time.
from vectra_artifacts.compilers import Compiler, CostModel, configure_dace, get_flags  # noqa: E402

# `timer(1) = elapsed_time * <scale>` in the .f90, where elapsed_time is in seconds.
TIMER_ASSIGN = re.compile(r"^\s*timer\(1\)\s*=\s*elapsed_time\s*\*\s*([0-9.eEdD+-]+)", re.IGNORECASE | re.MULTILINE)
TIMER_SECONDS = re.compile(r"^\s*elapsed_time\s*=\s*real\(finish\s*-\s*start,\s*8\)\s*/\s*real\(count_rate,\s*8\)",
                           re.IGNORECASE | re.MULTILINE)
TIMER_SLOT2 = re.compile(r"^\s*timer\(2\)\s*=", re.IGNORECASE | re.MULTILINE)


def load_variant(variant):
    """Import the variant's existing correctness harness as a module."""
    path = os.path.join(HERE, variant, f"run_{variant}.py")
    spec = importlib.util.spec_from_file_location(f"run_{variant}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fortran_timer_to_us(variant):
    """Factor converting this variant's ``timer(1)`` to microseconds, read from its own source.

    Returns ``(factor, slot2_written)``. Asserted per variant rather than assumed, because a
    silently mis-scaled timer would make every ratio in this report wrong but still plausible.
    """
    src = open(os.path.join(HERE, variant, f"{variant}_w_timer.f90")).read()
    if not TIMER_SECONDS.search(src):
        raise AssertionError(f"{variant}: elapsed_time is not seconds-from-system_clock; re-read the timer")
    m = TIMER_ASSIGN.search(src)
    if m is None:
        raise AssertionError(f"{variant}: no `timer(1) = elapsed_time * <scale>` found")
    scale = float(m.group(1).lower().replace("d", "e"))
    return 1.0e6 / scale, bool(TIMER_SLOT2.search(src))


def stats_us(samples):
    """min / median / max over the timed reps, in microseconds."""
    return min(samples), statistics.median(samples), max(samples)


def check_wall_bounds(label, timed_us, wall_us):
    """Fail loudly if the reported unit cannot be reconciled with the wall clock."""
    total = sum(timed_us)
    if total > wall_us * 1.05:
        raise AssertionError(f"{label}: reported {total:.1f} us > wall {wall_us:.1f} us -- unit is too large")
    if total < wall_us * 1e-3:
        raise AssertionError(f"{label}: reported {total:.1f} us < 0.1% of wall {wall_us:.1f} us -- unit is too small")


def fortran_lane(mod, variant, arrays, reps):
    """Run the original CloudSC Fortran, returning (outputs, cold_us, timed_us)."""
    to_us, slot2 = fortran_timer_to_us(variant)
    samples, out = [], None
    wall0 = time.perf_counter()
    for rep in range(reps + 1):
        timer = np.zeros(2)
        got = mod.run_original_fortran(arrays, timer_out=timer)
        if slot2 is False and timer[1] != 0.0:
            raise AssertionError(f"{variant}: timer(2) is never assigned in the .f90 but came back {timer[1]}")
        samples.append(timer[0] * to_us)
        if rep == 0:
            out = got
    wall = (time.perf_counter() - wall0) * 1e6
    check_wall_bounds(f"{variant} fortran", samples, wall)
    return out, samples[0], samples[1:]

def write_raw_data(variant, rows, compiler, cost_model, cluster):
    path = os.path.join(HERE, f"timing_results_{cluster}", f"raw_data_{variant}_{cost_model}_{compiler}.txt")
    with open(path, "w") as f:
        f.write("variant\tlane\trep\tus\n")
        for lane, samples in rows:
            for i, us in enumerate(samples, start=1):
                f.write(f"{variant}\t{lane}\t{i}\t{us:.6f}\n")
    return path


def dace_lane(mod, variant, frontend, arrays, reps, compiler=None, cost_model=None):
    """Run the compiled SDFG under Timer instrumentation, returning (outputs, cold_us, timed_us)."""
    import dace
    from dace.config import Config

    # One report spanning every invocation instead of one file per call, so the per-rep
    # durations come out of the instrumentation itself. Must precede codegen.
    Config.set("instrumentation", "report_each_invocation", value=False)
    sdfg = dace.SDFG.from_file(regen_sdfgs.sdfg_path(variant, frontend))
    # Isolate this cell's compiled build from every other (compiler, cost-model) cell.
    # Left at DaCe's default, every cell for a given variant/frontend shares the exact
    # same build_folder (.dacecache/<variant>_<frontend>_frontend/build) regardless of
    # compiler or cost-model -- so two cells compiling at once (e.g. a clang sweep job
    # and a gcc sweep job overlapping in time) raced on os.makedirs() for that shared
    # directory (FileExistsError: .../build) and could just as easily have silently
    # linked one cell's .so against another's half-written .o instead of failing loudly.
    # Scoping the folder per cell removes the possibility outright, independent of how
    # carefully the sweep jobs are sequenced. Cleared before every compile (not just
    # left to accumulate) so a stale .o from a previous run of this exact cell can't
    # silently survive into a "clean" rebuild -- scoped to only this cell's own folder,
    # so unlike a blanket `rm -rf .dacecache` in the caller, this can never touch a
    # different, concurrently-running cell's build directory.
    if compiler and cost_model:
        sdfg.build_folder = os.path.join(HERE, ".dacecache", f"{sdfg.name}_{compiler}_{cost_model}")
        shutil.rmtree(sdfg.build_folder, ignore_errors=True)
    sdfg.instrument = dace.InstrumentationType.Timer
    sdfg.clear_instrumentation_reports()
    csdfg = sdfg.compile()

    order = "F" if frontend == "fortran" else "C"
    live = {k: np.array(v, order=order, copy=True) for k, v in arrays.items()}
    kwargs = mod.sdfg_kwargs(f"{frontend}_frontend", live)
    out, wall = None, 0.0
    for rep in range(reps + 1):
        # These kernels accumulate in place, so every rep must start from the pristine
        # inputs. The refill sits outside the instrumented region either way.
        for k, v in arrays.items():
            np.copyto(live[k], v)
        t0 = time.perf_counter()
        csdfg(**kwargs)
        wall += (time.perf_counter() - t0) * 1e6
        if rep == 0:
            out = {k: live[k].copy() for k in mod.OUT}
    csdfg.finalize()  # __dace_exit flushes the accumulated report

    report = sdfg.get_latest_report()
    if report is None:
        raise AssertionError(f"{variant}/{frontend}: instrumentation produced no report")
    # DurationEvent.duration is raw microseconds; the report's `durations` dict is milliseconds.
    samples = [ev.duration for ev in report.events]
    if len(samples) != reps + 1:
        raise AssertionError(f"{variant}/{frontend}: {len(samples)} events for {reps + 1} calls")
    check_wall_bounds(f"{variant} dace/{frontend}", samples, wall)
    return out, samples[0], samples[1:]


def bench(variant, frontends, reps, regen, compiler, cost_model, cluster):
    """Run one variant end to end and return its report rows."""
    if regen:
        for frontend in frontends:
            regen_sdfgs.regen(variant, frontend)

    mod = load_variant(variant)
    arrays = mod.make_inputs()
    ref = mod.numpy_reference(arrays)
    to_us, slot2 = fortran_timer_to_us(variant)
    print(f"\n=== {variant} ===  rtol={mod.RTOL}  reps={reps}")
    print(f"  fortran timer(1) -> us factor {to_us:g}; timer(2) "
          f"{'assigned by the kernel' if slot2 else 'never assigned (unused slot)'}")

    rows = []
    raw_rows = []
    got, cold, timed = fortran_lane(mod, variant, arrays, reps)
    ok, msg = native.compare("Fortran vs NumPy", ref, got, mod.RTOL)
    rows.append(("original Fortran", stats_us(timed), cold, ok, msg))
    raw_rows.append(("original Fortran", timed))

    for frontend in frontends:
        got, cold, timed = dace_lane(mod, variant, frontend, arrays, reps, compiler, cost_model)
        ok, msg = native.compare(f"DaCe {frontend}-frontend vs NumPy", ref, got, mod.RTOL)
        rows.append((f"DaCe {frontend}-frontend", stats_us(timed), cold, ok, msg))
        raw_rows.append((f"DaCe {frontend}-frontend", timed))

    raw_path = write_raw_data(variant, raw_rows, compiler, cost_model, cluster)
    print(f"  wrote raw timing data to {raw_path}")
    for _, _, _, _, msg in rows:
        print("  " + msg)
    return rows


def report(results):
    """Print the summary table. Every timing column is microseconds."""
    print("\n" + "=" * 118)
    print(f"{'variant':<32}{'lane':<24}{'min_us':>10}{'median_us':>11}{'max_us':>10}"
          f"{'cold_us':>10}{'ratio_vs_F':>12}{'vs NumPy':>9}")
    print("-" * 118)
    for variant, rows in results:
        fortran_median = rows[0][1][1]
        for lane, (lo, med, hi), cold, ok, _ in rows:
            ratio = f"{fortran_median / med:.2f}x" if lane != "original Fortran" else "-"
            verdict = "PASS" if ok else "FAIL"
            # A timing number from a lane that failed its oracle check is never reported bare.
            mark = "" if ok else "  <- NUMERICALLY WRONG, timing not meaningful"
            print(f"{variant:<32}{lane:<24}{lo:>10.2f}{med:>11.2f}{hi:>10.2f}"
                  f"{cold:>10.2f}{ratio:>12}{verdict:>9}{mark}")
    print("-" * 118)
    print("all times microseconds; median/min/max over the timed reps, cold (first) rep excluded and shown "
          "separately;\nratio_vs_F = median original Fortran / median lane (>1 means the lane is faster)")


def configure_dace_from_environment(compiler_label, cost_model_label):
    """Apply the (compiler, cost-model, cpu) the caller sourced -- via one of
    scripts/source.<compiler>_<cpu>_<cost_model>.sh, which export CXX_COMPILER /
    CXX_COSTMODEL / CPU_NAME / CXX_MATH -- to DaCe's own compiler.cpu.* config.

    Previously sdfg.compile() (in dace_lane, below) just used whatever CC/CXX happened
    to be left over in the ambient shell env -- no cost-model flags reached the compile
    at all, and the compiler was only accidentally the intended one -- while
    --compiler/--cost_model only labelled the raw-data filename. Same class of bug
    already fixed in only_vec.py / only_vec_cloudsc_sdfg.py for the other two drivers;
    unlike those, this script calls sdfg.compile() in-process, so configure_dace() (an
    in-memory dace.config.Config mutation) is the right mechanism here -- there's no
    subprocess-isolation boundary for an env var to have to cross.

    Raises if --compiler/--cost_model (used for the raw-data filename) disagree with
    the sourced environment, so a mislabeled output file fails loudly at startup
    instead of silently reporting the wrong cell under the wrong name.
    """
    env_compiler = os.environ.get("CXX_COMPILER")
    env_cost_model = os.environ.get("CXX_COSTMODEL")
    if not env_compiler or not env_cost_model:
        print(
            "[bench_variants] WARNING: CXX_COMPILER/CXX_COSTMODEL not set in the "
            "environment -- source scripts/source.<compiler>_<cpu>_<cost_model>.sh "
            "before running this script, or DaCe compiles with its own untouched "
            "defaults (no cost-model flags applied, compiler unconfirmed).",
            file=sys.stderr,
        )
        return None

    if compiler_label and compiler_label != env_compiler:
        raise SystemExit(
            f"--compiler {compiler_label!r} does not match the sourced environment's "
            f"CXX_COMPILER={env_compiler!r} -- the raw-data filename would mislabel "
            f"what actually got compiled. Source the matching source.*.sh, or fix "
            f"--compiler."
        )
    if cost_model_label and cost_model_label != env_cost_model:
        raise SystemExit(
            f"--cost_model {cost_model_label!r} does not match the sourced "
            f"environment's CXX_COSTMODEL={env_cost_model!r} -- the raw-data filename "
            f"would mislabel what actually got compiled. Source the matching "
            f"source.*.sh, or fix --cost_model."
        )

    flag_set = get_flags(
        Compiler(env_compiler),
        CostModel(env_cost_model),
        math=os.environ.get("CXX_MATH") == "1",
        cpu=os.environ.get("CPU_NAME") or None,
    )
    configure_dace(flag_set)
    print(
        f"[bench_variants] DaCe compiler.cpu.* <- {flag_set.compiler.value}/"
        f"{flag_set.cost_model.value} (cpu={flag_set.cpu or 'unset'}, "
        f"executable={flag_set.compiler.executable()})"
    )
    return flag_set


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", choices=regen_sdfgs.VARIANTS, help="benchmark a single variant (default: all)")
    ap.add_argument("--reps", type=int, default=50, help="timed repetitions per lane (default 50)")
    ap.add_argument("--frontend", choices=("fortran", "python", "both"), default="both")
    ap.add_argument("--skip-regen", action="store_true", help="reuse the checked-in SDFGs instead of regenerating")
    ap.add_argument("--compiler", choices=("clang", "gcc"),
                     help="for the raw data output filename; must match the sourced source.*.sh's CXX_COMPILER")
    ap.add_argument("--cluster", choices=("eiger", "daint"), help="must pick a cluster (for the raw data output)")
    ap.add_argument("--cost_model", choices=("cheap", "default", "unlimited", "disabled"),
                     help="for the raw data output filename; must match the sourced source.*.sh's CXX_COSTMODEL")
    args = ap.parse_args()

    configure_dace_from_environment(args.compiler, args.cost_model)

    variants = (args.only, ) if args.only else regen_sdfgs.VARIANTS
    frontends = ("fortran", "python") if args.frontend == "both" else (args.frontend, )

    results, allok = [], True
    for variant in variants:
        rows = bench(variant, frontends, args.reps, not args.skip_regen, args.compiler, args.cost_model, args.cluster)
        results.append((variant, rows))
        allok = allok and all(ok for _, _, _, ok, _ in rows)
    report(results)
    print("\n" + ("ALL LANES MATCH THE NUMPY ORACLE" if allok else "SOME LANES DIVERGED FROM THE NUMPY ORACLE"))
    return 0 if allok else 1


if __name__ == "__main__":
    raise SystemExit(main())
