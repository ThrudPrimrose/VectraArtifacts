#!/usr/bin/env python3
"""
Compile and load TSVC microkernel shared libraries.

Each .cpp is compiled to a .o, then all .o files are linked into a single .so.

Usage:
    from compile_kernel import load_library, compile_library

    # Compile all kernels into one shared library
    so = compile_library("tsvc_cpp_microkernels")
    lib = ctypes.CDLL(str(so))
    lib.s277_d(a_ptr, b_ptr, c_ptr, d_ptr, e_ptr, iters, length, time_ptr)

    # Or use the convenience loader
    lib = load_library("tsvc_cpp_microkernels")
    lib.s277_d(...)
"""

import ctypes
import os
import pathlib
import subprocess
from typing import Optional

from compiler_config import CXX, COMPILE_FLAGS, LINK_FLAGS

# ---------------------------------------------------------------------------
#  Compiler configuration
# ---------------------------------------------------------------------------

_COMPILE_FLAGS = list(COMPILE_FLAGS)
_LINK_FLAGS = list(LINK_FLAGS)

BUILD_DIR = pathlib.Path(os.environ.get("TSVC_BUILD_DIR", ".tsvc_build"))
DEFAULT_SO_NAME = "libtsvc_kernels.so"


# ---------------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------------

def _obj_path(src: pathlib.Path, build_dir: pathlib.Path) -> pathlib.Path:
    """Deterministic .o path: <build_dir>/<stem>.o"""
    return build_dir / f"{src.stem}.o"


def _dep_path(obj: pathlib.Path) -> pathlib.Path:
    """Companion .d file emitted by -MMD."""
    return obj.with_suffix(".d")


def _parse_depfile(dep: pathlib.Path) -> list[pathlib.Path]:
    """
    Parse a GCC/Clang .d Makefile-style dependency file.

    Format:  target: dep1 dep2 \\
                     dep3 dep4
    Returns the list of dependency paths.
    """
    if not dep.exists():
        return []
    text = dep.read_text()
    # Strip the "target:" prefix
    _, _, rhs = text.partition(":")
    # Join continuation lines and split
    rhs = rhs.replace("\\\n", " ")
    return [pathlib.Path(p) for p in rhs.split() if p]


def _needs_rebuild(src: pathlib.Path, obj: pathlib.Path) -> bool:
    if not obj.exists():
        return True
    obj_mtime = obj.stat().st_mtime

    # Check the .d depfile — covers the source + every #included header
    deps = _parse_depfile(_dep_path(obj))
    if deps:
        for dep in deps:
            try:
                if dep.stat().st_mtime > obj_mtime:
                    return True
            except FileNotFoundError:
                # Header was deleted → must rebuild
                return True
        return False

    # Fallback if no .d file yet (first build)
    return src.stat().st_mtime > obj_mtime


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

def compile_object(
    src: str | pathlib.Path,
    build_dir: str | pathlib.Path = BUILD_DIR,
    extra_flags: Optional[list[str]] = None,
    force: bool = False,
) -> pathlib.Path:
    """
    Compile a single kernel .cpp into an object file (.o).

    Returns
    -------
    Path to the compiled .o
    """
    src = pathlib.Path(src).resolve()
    build_dir = pathlib.Path(build_dir).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)

    obj = _obj_path(src, build_dir)

    if not force and not _needs_rebuild(src, obj):
        return obj

    flags = list(_COMPILE_FLAGS)
    if extra_flags:
        flags.extend(extra_flags)

    cmd = [CXX, "-c"] + flags + [str(src), "-o", str(obj)]
    subprocess.check_call(cmd)
    return obj


def link_library(
    objects: list[pathlib.Path],
    build_dir: str | pathlib.Path = BUILD_DIR,
    so_name: str = DEFAULT_SO_NAME,
    extra_link_flags: Optional[list[str]] = None,
) -> pathlib.Path:
    """
    Link a list of .o files into a single shared library.

    Returns
    -------
    Path to the linked .so
    """
    build_dir = pathlib.Path(build_dir).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)

    so = build_dir / so_name

    flags = list(_LINK_FLAGS)
    if extra_link_flags:
        flags.extend(extra_link_flags)

    cmd = [CXX] + flags + [str(o) for o in objects] + ["-o", str(so)]
    subprocess.check_call(cmd)
    return so


def compile_library(
    root: str | pathlib.Path = "tsvc_cpp_microkernels",
    build_dir: str | pathlib.Path = BUILD_DIR,
    so_name: str = DEFAULT_SO_NAME,
    extra_flags: Optional[list[str]] = None,
    extra_link_flags: Optional[list[str]] = None,
    force: bool = False,
    pattern: str = "*.cpp",
    jobs: int = 1,
) -> pathlib.Path:
    """
    Compile every .cpp under *root* to .o, then link into a single .so.

    Returns
    -------
    Path to the final shared library.
    """
    root = pathlib.Path(root).resolve()
    cpps = sorted(root.rglob(pattern))

    if jobs > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        objects = []
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futs = {
                pool.submit(compile_object, cpp, build_dir, extra_flags, force): cpp
                for cpp in cpps
            }
            for fut in as_completed(futs):
                cpp = futs[fut]
                try:
                    objects.append(fut.result())
                except subprocess.CalledProcessError as e:
                    print(f"FAIL: {cpp.name}: {e}")
    else:
        objects = [compile_object(cpp, build_dir, extra_flags, force) for cpp in cpps]

    return link_library(objects, build_dir, so_name, extra_link_flags)


def load_library(
    root: str | pathlib.Path = "tsvc_cpp_microkernels",
    build_dir: str | pathlib.Path = BUILD_DIR,
    so_name: str = DEFAULT_SO_NAME,
    extra_flags: Optional[list[str]] = None,
    extra_link_flags: Optional[list[str]] = None,
    force: bool = False,
    pattern: str = "*.cpp",
    jobs: int = 1,
) -> ctypes.CDLL:
    """
    Compile and link all kernels, then load the single .so as a ctypes library.
    """
    so = compile_library(root, build_dir, so_name, extra_flags, extra_link_flags,
                         force, pattern, jobs)
    return ctypes.CDLL(str(so))


# ---------------------------------------------------------------------------
#  CLI: compile everything
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import time

    ap = argparse.ArgumentParser(description="Compile TSVC microkernels")
    ap.add_argument("root", nargs="?", default="tsvc_cpp_microkernels",
                    help="Root directory of kernel sources")
    ap.add_argument("-b", "--build-dir", default=str(BUILD_DIR))
    ap.add_argument("-o", "--so-name", default=DEFAULT_SO_NAME,
                    help="Output shared library name")
    ap.add_argument("-f", "--force", action="store_true", help="Force rebuild")
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count(),
                    help="Parallel compile jobs (default: nproc)")
    ap.add_argument("--pattern", default="*.cpp")
    args = ap.parse_args()

    root = pathlib.Path(args.root).resolve()
    build_dir = pathlib.Path(args.build_dir).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)

    cpps = sorted(root.rglob(args.pattern))
    print(f"Found {len(cpps)} source files under {root}")

    t0 = time.perf_counter()

    # Phase 1: compile .cpp -> .o
    if args.jobs > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        objects = []
        compiled = 0
        cached = 0
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futs = {
                pool.submit(compile_object, cpp, build_dir, force=args.force): cpp
                for cpp in cpps
            }
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
        objects = []
        for cpp in cpps:
            objects.append(compile_object(cpp, build_dir, force=args.force))

    # Phase 2: link all .o -> single .so
    so = link_library(objects, build_dir, args.so_name)
    dt = time.perf_counter() - t0
    print(f"Linked {len(objects)} objects -> {so}")
    print(f"Done in {dt:.1f}s")