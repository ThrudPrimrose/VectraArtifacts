"""Compile per-kernel ``.cpp`` files into a single shared library.

Walks a ``microkernels_cpp/`` root for ``*.cpp`` files, compiles each
to ``.o`` with header-aware dependency tracking, then links them all
into one ``.so``. Shared by tsvc_2 and tsvc_2_5.
"""
import argparse
import ctypes
import os
import pathlib
import subprocess
from typing import List, Optional

from compiler_config import CXX, COMPILE_FLAGS, LINK_FLAGS  # repo-root shim


def _obj_path(src: pathlib.Path, build_dir: pathlib.Path) -> pathlib.Path:
    return build_dir / f"{src.stem}.o"


def _dep_path(obj: pathlib.Path) -> pathlib.Path:
    return obj.with_suffix(".d")


def _parse_depfile(dep: pathlib.Path) -> List[pathlib.Path]:
    """Parse a GCC/Clang ``.d`` Makefile-style dependency file. Empty
    list if the file is missing."""
    if not dep.exists():
        return []
    _, _, rhs = dep.read_text().partition(":")
    rhs = rhs.replace("\\\n", " ")
    return [pathlib.Path(p) for p in rhs.split() if p]


def _needs_rebuild(src: pathlib.Path, obj: pathlib.Path) -> bool:
    """True if any compile input (source or transitively-included
    header) is newer than the object file. Falls back to source-only
    when no ``.d`` is present yet."""
    if not obj.exists():
        return True
    obj_mtime = obj.stat().st_mtime
    deps = _parse_depfile(_dep_path(obj))
    if deps:
        for dep in deps:
            try:
                if dep.stat().st_mtime > obj_mtime:
                    return True
            except FileNotFoundError:
                return True
        return False
    return src.stat().st_mtime > obj_mtime


def _vec_report_flag() -> List[str]:
    """Return the compiler flag(s) that emit vectorization remarks to stderr.

    * GCC:   ``-fopt-info-vec-missed``  (reports both vectorized and missed)
        * may want to switch it to -fopt-info-vec-all, to get details on both missed and vectorised
    * Clang: ``-Rpass=loop-vectorize -Rpass-missed=loop-vectorize``
    * ICPX:  ``-qopt-report=2 -qopt-report-phase=vec``  (writes a .optrpt file)
    """
    cxx_lower = CXX.lower()
    if "clang" in cxx_lower:
        return ["-Rpass=loop-vectorize", "-Rpass-missed=loop-vectorize"]
    if "icpx" in cxx_lower or "icpc" in cxx_lower:
        return ["-qopt-report=2", "-qopt-report-phase=vec"]
    # GCC default
    return ["-fopt-info-vec-all"]


def compile_object(src,
                   build_dir,
                   extra_flags: Optional[List[str]] = None,
                   force: bool = False,
                   vec_report: bool = False) -> pathlib.Path:
    """Compile a single ``.cpp`` to its ``.o``. Returns the ``.o``
    path; skips the spawn if dependency tracking says it's fresh.

    When *vec_report* is ``True`` the compiler's vectorization remarks are
    written to ``<obj>.rpt`` next to the object file so that
    :func:`parse_vec_reports` can classify each kernel later.
    """
    src = pathlib.Path(src).resolve()
    build_dir = pathlib.Path(build_dir).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    obj = _obj_path(src, build_dir)
    if not force and not _needs_rebuild(src, obj):
        return obj
    flags = list(COMPILE_FLAGS)
    if extra_flags:
        flags.extend(extra_flags)
    if vec_report:
        flags.extend(_vec_report_flag())
    rpt_path = obj.with_suffix(".rpt")
    result = subprocess.run(
        [CXX, "-c"] + flags + [str(src), "-o", str(obj)],
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, result.args, stderr=result.stderr)
    if vec_report:
        rpt_path.write_text(result.stderr)
    return obj


def parse_vec_reports(build_dir) -> dict:
    """Parse all ``*.rpt`` files in *build_dir* and return a mapping of
    ``kernel_name -> bool`` where ``True`` means at least one loop was
    reported as vectorized.

    Supports GCC (``loop vectorized``), Clang (``vectorized loop``), and
    ICPX (``LOOP AUTO-VECTORIZED``).
    """
    import re
    build_dir = pathlib.Path(build_dir)
    vec_re = re.compile(
        r"optimized: loop vectorized"  # GCC (-fopt-info-vec)
        r"|vectorized loop"            # Clang (-Rpass=loop-vectorize)
        r"|LOOP AUTO-VECTORIZED",      # ICPX (-qopt-report)
        re.IGNORECASE,
    )
    results = {}
    for rpt in sorted(build_dir.glob("*.rpt")):
        kernel = rpt.stem  # e.g. "s111_d" -> strip _d/_f suffix below
        # Kernel files are named <name>_d.cpp / <name>_f.cpp; strip the suffix.
        kernel = re.sub(r"_[df]$", "", kernel)
        text = rpt.read_text()
        was_vectorized = bool(vec_re.search(text))
        # Merge double/float variants: vectorized if either was
        results[kernel] = results.get(kernel, False) or was_vectorized
    return results


def link_library(
    objects: List[pathlib.Path],
    build_dir,
    so_name: str,
    extra_link_flags: Optional[List[str]] = None,
) -> pathlib.Path:
    """Link ``objects`` into ``<build_dir>/<so_name>``."""
    build_dir = pathlib.Path(build_dir).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    so = build_dir / so_name
    flags = list(LINK_FLAGS)
    if extra_link_flags:
        flags.extend(extra_link_flags)
    subprocess.check_call([CXX] + flags + [str(o) for o in objects] + ["-o", str(so)])
    return so


def compile_cpp_library(
    root,
    build_dir,
    so_name: str,
    extra_flags: Optional[List[str]] = None,
    extra_link_flags: Optional[List[str]] = None,
    force: bool = False,
    pattern: str = "*.cpp",
    jobs: int = 1,
    vec_report: bool = False,
) -> pathlib.Path:
    """Compile every kernel under ``root`` and link them into one
    ``.so``. ``jobs > 1`` uses a thread pool around the per-file
    compile.

    When *vec_report* is ``True`` each kernel's vectorization remarks are
    written to ``<build_dir>/<kernel>.rpt``. Use :func:`parse_vec_reports`
    afterwards to read the results.
    """
    root = pathlib.Path(root).resolve()
    cpps = sorted(root.rglob(pattern))

    if jobs > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        objects: List[pathlib.Path] = []
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futs = {pool.submit(compile_object, cpp, build_dir, extra_flags, force, vec_report): cpp for cpp in cpps}
            for fut in as_completed(futs):
                cpp = futs[fut]
                try:
                    objects.append(fut.result())
                except subprocess.CalledProcessError as e:
                    print(f"FAIL: {cpp.name}: {e}")
    else:
        objects = [compile_object(cpp, build_dir, extra_flags, force, vec_report) for cpp in cpps]

    return link_library(objects, build_dir, so_name, extra_link_flags)


def load_cpp_library(root, build_dir, so_name: str, **kwargs) -> ctypes.CDLL:
    """:func:`compile_cpp_library` + ``ctypes.CDLL`` wrapper."""
    so = compile_cpp_library(root, build_dir, so_name, **kwargs)
    return ctypes.CDLL(str(so))


def main_compile_cpp(default_root: str,
                     default_build_dir: str,
                     default_so_name: str,
                     argv: "list | None" = None) -> int:
    """Argparse wrapper used by ``tsvc_2/`` and ``tsvc_2_5/`` entry points."""
    import time
    ap = argparse.ArgumentParser(description="Compile per-kernel .cpp into a single shared library.")
    ap.add_argument("root", nargs="?", default=default_root, help="Root directory of kernel sources.")
    ap.add_argument("-b", "--build-dir", default=default_build_dir)
    ap.add_argument("-o", "--so-name", default=default_so_name)
    ap.add_argument("-f", "--force", action="store_true")
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count())
    ap.add_argument("--pattern", default="*.cpp")
    ap.add_argument("--vec-report", action="store_true", help="Capture vectorization remarks into <build_dir>/*.rpt files.")
    ap.add_argument("--vec-report-out", default=None, metavar="FILE", help="Write the summary table to FILE (default: <so_name>.vec_report.txt "
                         "when --vec-report is set, else no file).")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.root).resolve()
    cpps = sorted(root.rglob(args.pattern))
    print(f"Found {len(cpps)} source files under {root}")

    t0 = time.perf_counter()
    if args.jobs > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        objects: List[pathlib.Path] = []
        compiled = cached = 0
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futs = {pool.submit(compile_object, cpp, args.build_dir, force=args.force, vec_report=args.vec_report): cpp for cpp in cpps}
            for fut in as_completed(futs):
                cpp = futs[fut]
                try:
                    obj = fut.result()
                    objects.append(obj)
                    if _needs_rebuild(cpp, obj):
                        compiled += 1
                    else:
                        cached += 1
                except subprocess.CalledProcessError as e:
                    print(f"FAIL: {cpp.name}: {e}")
                    compiled += 1
        print(f"Compile: {compiled} compiled, {cached} cached")
    else:
        objects = [compile_object(cpp, args.build_dir, force=args.force, vec_report=args.vec_report) for cpp in cpps]

    so = link_library(objects, args.build_dir, args.so_name)
    print(f"Linked {len(objects)} objects -> {so}")

    if args.vec_report:
        results = parse_vec_reports(args.build_dir)
        vec_count = sum(1 for v in results.values() if v)
        print(f"Vectorization report: {vec_count}/{len(results)} kernels vectorized")
        header = f"Vectorization report: {vec_count}/{len(results)} kernels vectorized"
        lines = [header]
        for name, vec in sorted(results.items()):
            status = "VEC" if vec else "---"
            print(f"  {status}  {name}")
            lines.append(f"  {status}  {name}")

        report_text = "\n".join(lines) + "\n"
        print(report_text, end="")

        # Determine output file: explicit --vec-report-out, or auto-named.
        out_path = args.vec_report_out
        if out_path is None:
            so_stem = pathlib.Path(args.so_name).stem  # e.g. "libtsvc_kernels"
            out_path = pathlib.Path(args.build_dir) / f"{so_stem}.vec_report.txt"
        else:
            out_path = pathlib.Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_text)
        print(f"Saved report -> {out_path}")

    print(f"Done in {time.perf_counter() - t0:.1f}s")
    return 0
