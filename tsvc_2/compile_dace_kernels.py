#!/usr/bin/env python3
"""
Compile DaCe microkernel SDFGs.

Each .py module under tsvc_dace_microkernels is imported, converted to an SDFG
via to_sdfg(), and compiled.  Multiprocessing is used for parallelism (DaCe
compilation is CPU-heavy and releases the GIL poorly).

Usage:
    # CLI: compile everything
    python compile_dace_kernels.py [tsvc_dace_microkernels] [-j 8] [-f]

    # API
    from compile_dace_kernels import compile_all_dace_kernels
    results = compile_all_dace_kernels("tsvc_dace_microkernels", jobs=8)
"""

import contextlib
import importlib
import importlib.util
import os
import pathlib
import sys
import traceback
from typing import Optional

BUILD_DIR = pathlib.Path(os.environ.get("DACE_BUILD_DIR", ".dace_build"))


# ---------------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------------

def _import_module_from_path(py_file: pathlib.Path):
    """Import a .py file as a module without polluting sys.modules."""
    mod_name = py_file.stem
    spec = importlib.util.spec_from_file_location(mod_name, str(py_file))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load spec for {py_file}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _find_dace_program(mod):
    """
    Find the DaCe program in a module.

    Looks for:
      1. A function decorated with @dace.program (has __sdfg__ or to_sdfg)
      2. An attribute named 'kernel' or matching the module name
    """
    import dace

    candidates = []
    for name in dir(mod):
        if name.startswith("_"):
            continue
        obj = getattr(mod, name)
        if hasattr(obj, "to_sdfg"):
            candidates.append((name, obj))
        elif isinstance(obj, dace.SDFG):
            candidates.append((name, obj))

    if len(candidates) == 1:
        return candidates[0]
    for cname, cobj in candidates:
        if cname == mod.__name__ or cname == mod.__name__.removesuffix("_d").removesuffix("_f"):
            return (cname, cobj)
    if candidates:
        return candidates[0]
    return None, None


@contextlib.contextmanager
def _suppress_fd():
    """
    Redirect OS-level stdout and stderr to /dev/null.

    This catches output from subprocesses (CMake, make) that bypass
    Python's sys.stdout/sys.stderr.
    """
    devnull = os.open(os.devnull, os.O_WRONLY)
    old_stdout = os.dup(1)
    old_stderr = os.dup(2)
    try:
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        yield
    finally:
        os.dup2(old_stdout, 1)
        os.dup2(old_stderr, 2)
        os.close(old_stdout)
        os.close(old_stderr)
        os.close(devnull)


def _compile_one_kernel(py_file: pathlib.Path, build_dir: pathlib.Path, force: bool) -> dict:
    """
    Import a single kernel module, convert to SDFG, and compile.

    Returns a result dict with status info.
    """
    import dace

    # Apply shared compiler flags via DaCe config
    from compiler_config import configure_dace
    configure_dace()

    # Ensure CMake can find compilers in worker subprocesses
    if "CC" not in os.environ:
        os.environ["CC"] = "gcc"
    if "CXX" not in os.environ:
        os.environ["CXX"] = "g++"

    result = {
        "file": str(py_file),
        "stem": py_file.stem,
        "status": "unknown",
        "error": None,
    }

    try:
        mod = _import_module_from_path(py_file)
        name, prog = _find_dace_program(mod)

        if prog is None:
            result["status"] = "skipped"
            result["error"] = "no @dace.program or SDFG found"
            return result

        # Get or build the SDFG
        if isinstance(prog, dace.SDFG):
            sdfg = prog
        else:
            sdfg = prog.to_sdfg()

        sdfg.name = py_file.stem

        # Each kernel gets its own isolated build folder so that parallel
        # CMake invocations don't race on the same CompilerIdCXX directory.
        kernel_build_dir = build_dir / sdfg.name
        kernel_build_dir.mkdir(parents=True, exist_ok=True)
        sdfg.build_folder = str(kernel_build_dir)

        # Check if already compiled (unless forced)
        so_path = kernel_build_dir / sdfg.name / "build" / f"lib{sdfg.name}.so"
        if not force and so_path.exists():
            result["status"] = "cached"
            return result

        # Suppress CMake/compiler stdout+stderr (comes from subprocesses,
        # so we must redirect at the OS file-descriptor level).
        with _suppress_fd():
            sdfg.compile()
        result["status"] = "compiled"

    except Exception as e:
        result["status"] = "failed"
        result["error"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"

    return result


def _compile_worker(args):
    """Multiprocessing worker — unpacks args tuple."""
    py_file, build_dir, force = args
    return _compile_one_kernel(
        pathlib.Path(py_file),
        pathlib.Path(build_dir),
        force,
    )


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

def compile_all_dace_kernels(
    root: str | pathlib.Path = "tsvc_dace_microkernels",
    build_dir: str | pathlib.Path = BUILD_DIR,
    force: bool = False,
    pattern: str = "*.py",
    jobs: int = 1,
) -> list[dict]:
    """
    Compile every DaCe kernel .py under *root*.

    Parameters
    ----------
    root      : Root directory of kernel sources
    build_dir : Where DaCe puts compiled SDFGs
    force     : Recompile even if .so exists
    pattern   : Glob pattern for source files
    jobs      : Number of parallel workers (multiprocessing)

    Returns
    -------
    List of result dicts with keys: file, stem, status, error
    """
    root = pathlib.Path(root).resolve()
    build_dir = pathlib.Path(build_dir).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)

    py_files = sorted(
        f for f in root.rglob(pattern)
        if f.name != "__init__.py" and not f.name.startswith("_")
    )

    if not py_files:
        print(f"No kernel files found under {root} with pattern '{pattern}'")
        return []

    work_items = [(str(f), str(build_dir), force) for f in py_files]

    if jobs > 1:
        from multiprocessing import Pool

        with Pool(processes=jobs) as pool:
            results = pool.map(_compile_worker, work_items)
    else:
        results = [_compile_worker(item) for item in work_items]

    return results


# ---------------------------------------------------------------------------
#  CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import time

    ap = argparse.ArgumentParser(description="Compile DaCe TSVC microkernels")
    ap.add_argument(
        "root",
        nargs="?",
        default="tsvc_dace_microkernels",
        help="Root directory of DaCe kernel sources",
    )
    ap.add_argument("-b", "--build-dir", default=str(BUILD_DIR))
    ap.add_argument("-f", "--force", action="store_true", help="Force recompile")
    ap.add_argument(
        "-j", "--jobs", type=int, default=os.cpu_count(),
        help="Parallel compile jobs (default: nproc)",
    )
    ap.add_argument("--pattern", default="*.py")
    args = ap.parse_args()

    root = pathlib.Path(args.root).resolve()
    py_files = sorted(
        f for f in root.rglob(args.pattern)
        if f.name != "__init__.py" and not f.name.startswith("_")
    )
    print(f"Found {len(py_files)} DaCe kernel files under {root}")

    t0 = time.perf_counter()
    results = compile_all_dace_kernels(
        root=args.root,
        build_dir=args.build_dir,
        force=args.force,
        pattern=args.pattern,
        jobs=args.jobs,
    )
    dt = time.perf_counter() - t0

    # Summary
    compiled = sum(1 for r in results if r["status"] == "compiled")
    cached = sum(1 for r in results if r["status"] == "cached")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"] == "failed")

    for r in results:
        if r["status"] == "failed":
            print(f"  FAIL: {r['stem']}: {r['error']}")
        elif r["status"] == "skipped":
            print(f"  SKIP: {r['stem']}: {r['error']}")

    if failed or skipped:
        print(f"\n{compiled} compiled, {cached} cached, {skipped} skipped, {failed} failed")
    print(f"Done in {dt:.1f}s")