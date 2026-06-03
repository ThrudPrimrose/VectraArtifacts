"""Compile per-kernel DaCe ``.py`` files into per-kernel SDFG ``.so``.

Each kernel file under ``microkernels_dace/<kernel>/<kernel>_d.py``
exports one ``@dace.program``; we import it, convert to an SDFG, and
compile under an isolated build folder. Multiprocessing is used per
file because DaCe's compile path is CPU-heavy and the GIL-bound work
inside it serializes thread pools poorly.
"""
import argparse
import contextlib
import importlib.util
import os
import pathlib
import sys
import traceback
from typing import List, Optional


def _import_module_from_path(py_file: pathlib.Path):
    """Import a ``.py`` file as a module without polluting ``sys.modules``."""
    spec = importlib.util.spec_from_file_location(py_file.stem, str(py_file))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load spec for {py_file}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _find_dace_program(mod):
    """Return ``(name, program)`` for the kernel exposed by the module.

    Pick the single callable with ``to_sdfg`` (the canonical case);
    fall back to the attribute that matches the module name when
    multiple candidates exist."""
    import dace
    candidates = []
    for name in dir(mod):
        if name.startswith("_"):
            continue
        obj = getattr(mod, name)
        if hasattr(obj, "to_sdfg") or isinstance(obj, dace.SDFG):
            candidates.append((name, obj))
    if len(candidates) == 1:
        return candidates[0]
    for cname, cobj in candidates:
        if cname == mod.__name__ or cname == mod.__name__.removesuffix("_d").removesuffix("_f"):
            return (cname, cobj)
    return candidates[0] if candidates else (None, None)


@contextlib.contextmanager
def _suppress_fd():
    """Silence OS-level stdout/stderr (catches CMake / clang output
    from subprocesses that bypass Python's ``sys.stdout``)."""
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
    """Compile a single kernel module into ``<build_dir>/<kernel>``.

    Returns a result dict with ``status`` in ``{compiled, cached,
    skipped, failed}``; ``error`` carries the traceback on failure."""
    import dace
    from compiler_config import configure_dace
    configure_dace()

    if "CC" not in os.environ:
        os.environ["CC"] = "gcc"
    if "CXX" not in os.environ:
        os.environ["CXX"] = "g++"

    result = {"file": str(py_file), "stem": py_file.stem, "status": "unknown", "error": None}
    try:
        mod = _import_module_from_path(py_file)
        name, prog = _find_dace_program(mod)
        if prog is None:
            result["status"] = "skipped"
            result["error"] = "no @dace.program or SDFG found"
            return result

        sdfg = prog if isinstance(prog, dace.SDFG) else prog.to_sdfg()
        sdfg.name = py_file.stem

        kernel_build_dir = build_dir / sdfg.name
        kernel_build_dir.mkdir(parents=True, exist_ok=True)
        sdfg.build_folder = str(kernel_build_dir)

        so_path = kernel_build_dir / sdfg.name / "build" / f"lib{sdfg.name}.so"
        if not force and so_path.exists():
            result["status"] = "cached"
            return result

        with _suppress_fd():
            sdfg.compile()
        result["status"] = "compiled"
    except Exception as e:
        result["status"] = "failed"
        result["error"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    return result


def _compile_worker(args):
    py_file, build_dir, force = args
    return _compile_one_kernel(pathlib.Path(py_file), pathlib.Path(build_dir), force)


def compile_dace_all(
    root,
    build_dir,
    force: bool = False,
    pattern: str = "*.py",
    jobs: int = 1,
) -> List[dict]:
    """Compile every kernel ``.py`` under ``root``. Returns one result
    dict per kernel (``status``, ``error``)."""
    root = pathlib.Path(root).resolve()
    build_dir = pathlib.Path(build_dir).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)

    py_files = sorted(f for f in root.rglob(pattern) if f.name != "__init__.py" and not f.name.startswith("_"))
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


def main_compile_dace(default_root: str, default_build_dir: str, argv: "list | None" = None) -> int:
    """Argparse wrapper used by ``tsvc_2/`` and ``tsvc_2_5/`` entry points."""
    import time
    ap = argparse.ArgumentParser(description="Compile per-kernel DaCe .py SDFGs in parallel.")
    ap.add_argument("root", nargs="?", default=default_root)
    ap.add_argument("-b", "--build-dir", default=default_build_dir)
    ap.add_argument("-f", "--force", action="store_true")
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count())
    ap.add_argument("--pattern", default="*.py")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.root).resolve()
    py_files = sorted(f for f in root.rglob(args.pattern) if f.name != "__init__.py" and not f.name.startswith("_"))
    print(f"Found {len(py_files)} DaCe kernel files under {root}")

    t0 = time.perf_counter()
    results = compile_dace_all(root=args.root,
                               build_dir=args.build_dir,
                               force=args.force,
                               pattern=args.pattern,
                               jobs=args.jobs)
    dt = time.perf_counter() - t0

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
    return 0
