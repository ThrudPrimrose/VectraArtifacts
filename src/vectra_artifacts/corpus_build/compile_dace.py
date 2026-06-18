#!/usr/bin/env python3
"""compile_dace.py — compile and time DaCe TSVC-2 kernels."""

from __future__ import annotations

import argparse
import ast
import base64
import ctypes
import fnmatch
import importlib.util
import json
import multiprocessing
import pathlib
import pickle
import re
import statistics
import subprocess
import sys
import tempfile
import time as _time
import os
from typing import Optional

import numpy as np

# ── ctypes pointer aliases ─────────────────────────────────────────────────────
_dp   = ctypes.POINTER(ctypes.c_double)
_fp   = ctypes.POINTER(ctypes.c_float)
_ip   = ctypes.POINTER(ctypes.c_int)
_i64p = ctypes.POINTER(ctypes.c_int64)


# ── SIGNATURES loader ──────────────────────────────────────────────────────────
def _load_signatures(root: pathlib.Path):
    """Infer the correct bindings file from 'tsvc_2_5' or 'tsvc_2' in root."""
    import importlib.util

    root_str = str(root)

    # Check tsvc_2_5 first — it must come before tsvc_2 because tsvc_2_5
    # also contains the substring "tsvc_2".
    if "tsvc_2_5" in root_str:
        bindings_rel = "tsvc_2_5/tsvc_2_5_bindings.py"
    elif "tsvc_2" in root_str:
        bindings_rel = "tsvc_2/tsvc_bindings.py"
    else:
        print(f"  [timing] ERROR: cannot infer TSVC version from root path: {root}",
              flush=True)
        return None

    # Anchor the bindings file relative to cwd (where the user runs the script from)
    bindings_path = pathlib.Path.cwd() / bindings_rel

    if not bindings_path.exists():
        print(f"  [timing] ERROR: bindings file not found: {bindings_path}", flush=True)
        return None

    spec = importlib.util.spec_from_file_location("_tsvc_bindings_tmp", bindings_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    sigs = getattr(mod, "SIGNATURES", None)

    if not sigs:
        print(f"  [timing] ERROR: no SIGNATURES found in {bindings_path}", flush=True)
        return None

    print(f"  location of signature to load:  {bindings_path}", flush=True)
    return sigs


# ── DaCe signature overrides removed ─────────────────────────────────────────
# Signature matching is handled purely via the pool: every parameter name that
# appears in SIGNATURES must have a corresponding entry in _make_array_pool().
# To fix a SKIP, add the missing key to the pool — do not filter signatures.


# ── Array pool ─────────────────────────────────────────────────────────────────
def _make_array_pool(len_1d: int, is_float: bool) -> dict:
    dtype  = np.float32 if is_float else np.float64
    rng    = np.random.default_rng(42)
    SSYM   = 4
    S_TILE = 32
    T_TILE = 32

    dim_2d  = min(len_1d, 4096)
    arr_2d  = rng.random((dim_2d, dim_2d)).astype(dtype)
    dim_3d  = 32
    arr_3d  = rng.random((dim_3d, dim_3d, dim_3d)).astype(dtype)
    idx_arr = np.mod(np.arange(len_1d, dtype=np.int64) * 7 + 3, len_1d)

    return {
        "a": arr_2d.ravel(), "b": arr_2d.ravel().copy(),
        "c": rng.random(len_1d).astype(dtype),
        "d": rng.random(len_1d).astype(dtype),
        "e": rng.random(len_1d).astype(dtype),
        "f": rng.random(len_1d).astype(dtype),
        "g": rng.random(len_1d).astype(dtype),
        "h": rng.random(len_1d).astype(dtype),
        "u": rng.random(len_1d).astype(dtype),
        "v": rng.random(len_1d).astype(dtype),
        "w": rng.random(len_1d).astype(dtype),
        "x": rng.random(len_1d).astype(dtype),
        "y": rng.random(len_1d).astype(dtype),
        "z": rng.random(len_1d).astype(dtype),
        # tsvc_2 uses aa/bb/cc as 2D arrays: aa[len_2d][len_1d]
        # Must be len_2d * len_1d elements to avoid out-of-bounds SIGSEGV
        "aa": rng.random(dim_2d * len_1d).astype(dtype),
        "bb": rng.random(dim_2d * len_1d).astype(dtype),
        "cc": rng.random(dim_2d * len_1d).astype(dtype),
        "dd": rng.random(dim_2d * len_1d).astype(dtype),
        "xx": rng.random(len_1d).astype(dtype),
        "p": rng.random(len_1d).astype(dtype),
        "q": rng.random(len_1d).astype(dtype),
        "r": rng.random(len_1d).astype(dtype),
        "in_": rng.random(len_1d).astype(dtype),
        "src": rng.random(len_1d).astype(dtype),
        "dst": rng.random(SSYM * len_1d).astype(dtype),
        "out": np.zeros(1, dtype=dtype),
        "threshold_data": rng.random(len_1d).astype(dtype),
        "a_2d": arr_2d.ravel(), "b_2d": arr_2d.ravel().copy(),
        "a_3d": arr_3d.ravel(), "b_3d": arr_3d.ravel().copy(),
        "ip": idx_arr.copy(), "idx": idx_arr.copy(),
        "index": idx_arr.copy(), "ind": idx_arr.copy(),
        "mask": rng.integers(0, 2, size=len_1d, dtype=np.int64),
        "scale": 1.0, "alpha": 1.0, "beta": 0.5, "gamma": 0.25,
        "s": 1.0, "t": 1.0,
        "n": len_1d, "m": len_1d,
        "len_1d": len_1d, "LEN_1D": len_1d,
        "LEN_2D": dim_2d, "LEN_3D": dim_3d,
        "len_2d": dim_2d, "len_3d": dim_3d,
        "ntimes": len_1d, "iterations": len_1d,
        "K": 1, "k": 1, "k1": 1, "k2": len_1d // 4,
        "SSYM": SSYM, "ssym": SSYM,
        "S": S_TILE, "T": T_TILE,
        "s_tile": S_TILE, "t_tile": T_TILE, "tile_size": T_TILE,
        "stride": 4, "offset": 1, "wrap_size": len_1d,
        "nx": dim_3d, "ny": dim_3d, "nz": dim_3d, "nt": 2,
        # jacobi2d_double_tiled_sym_d: two symbolic tile sizes
        "t1": 64,
        "t2": 8,
        # tsvc_2 missing scalars
        "vlen": 8,
        "n1": 1,
        "n3": len_1d - 1,
        "inc": 1,
        "M": len_1d // 4,
        "s1": 1.0,
        "s2": 2.0,
        "threshold": 0.5,
        "j": 0,
        # tsvc_2 reduction output scalars
        "sum_out": np.zeros(1, dtype=dtype),
        "result": np.zeros(1, dtype=dtype),
        "result_out": np.zeros(1, dtype=dtype),
        "dot": np.zeros(1, dtype=dtype),
        "dot_out": np.zeros(1, dtype=dtype),
        # tsvc_2 flat 2D arrays — must be dim_2d * dim_2d (square) since
        # kernels like s125 index up to LEN_2D*LEN_2D-1
        "flat": rng.random(dim_2d * dim_2d).astype(dtype),
        "flat_2d_array": rng.random(dim_2d * dim_2d).astype(dtype),
        # tsvc_2 integer index array (int32)
        "indx": np.mod(
            np.arange(len_1d, dtype=np.int32) * 7 + 3, len_1d
        ).astype(np.int32),
    }


# ── ctypes helpers ─────────────────────────────────────────────────────────────
def _is_pointer_ctype(ct) -> bool:
    name = getattr(ct, "__name__", "") or ""
    return name.startswith("LP_") or hasattr(ct, "contents") or ct in (_dp, _fp, _ip, _i64p)

def _is_int64_ctype(ct) -> bool:
    name = getattr(ct, "__name__", "") or ""
    return name in ("LP_c_long", "LP_c_int64", "LP_c_longlong") or ct is _i64p

def _array_to_ptr(arr: np.ndarray, ctype_d, is_float: bool):
    ct_name = getattr(ctype_d, "__name__", "") or ""
    if _is_int64_ctype(ctype_d):
        return arr.astype(np.int64, copy=False).ctypes.data_as(ctypes.POINTER(ctypes.c_int64))
    if ctype_d is _ip or ct_name in ("LP_c_int", "LP_c_int32"):
        return arr.astype(np.int32, copy=False).ctypes.data_as(_ip)
    if is_float:
        a = arr.astype(np.float32) if arr.dtype != np.float32 else arr
        return a.ctypes.data_as(_fp)
    a = arr.astype(np.float64) if arr.dtype != np.float64 else arr
    return a.ctypes.data_as(_dp)

def _build_dace_ctypes_args(sig, pool: dict, is_float: bool):
    call_args, keep_alive = [], []
    for pname, ctype_d, ctype_f in sig:
        val = pool.get(pname)
        if val is None:
            return None, None
        if _is_pointer_ctype(ctype_d):
            if not isinstance(val, np.ndarray):
                if _is_int64_ctype(ctype_d):
                    val = np.array([int(val)], dtype=np.int64)
                elif (getattr(ctype_d, "__name__", "") or "").startswith("LP_c_int"):
                    val = np.array([int(val)], dtype=np.int32)
                elif is_float:
                    val = np.array([float(val)], dtype=np.float32)
                else:
                    val = np.array([float(val)], dtype=np.float64)
                keep_alive.append(val)
            call_args.append(_array_to_ptr(val, ctype_d, is_float))
        else:
            # Use the sig's declared ctype directly so 32-bit vs 64-bit scalars
            # match the compiled ABI exactly (c_int vs c_int64 vs c_double etc.)
            ct = ctype_f if is_float else ctype_d
            try:
                buf = ct(float(val) if 'double' in ct.__name__ or 'float' in ct.__name__ else int(val))
            except Exception:
                buf = ctypes.c_int64(int(val))  # safe fallback
            keep_alive.append(buf)
            call_args.append(buf)
    return call_args, keep_alive


# ── Source-order helper ────────────────────────────────────────────────────────
def _sig_order_from_source(py_path: pathlib.Path, base: str) -> "list[str] | None":
    try:
        tree = ast.parse(py_path.read_text())
    except (SyntaxError, OSError):
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in (
            base, f"{base}_d", f"{base}_f", f"{base}_d_single", f"{base}_f_single"
        ):
            return [a.arg for a in node.args.args]
    return None

def _find_dylib(kdir: pathlib.Path, stem: str) -> Optional[pathlib.Path]:
    """
    Find the pre-built dacestub shared library for a DaCe kernel.

    Both tsvc_2 and tsvc_2_5 use the same modular layout:
        <kdir>/build/<stem>_<stem>_<hash>/build/libdacestub_<stem>_<stem>.dylib
    """
    build = kdir / "build"
    if not build.is_dir():
        return None

    candidates: list[pathlib.Path] = []
    for sub in build.iterdir():
        if not sub.is_dir() or not sub.name.startswith(f"{stem}_"):
            continue
        sub_build = sub / "build"
        if not sub_build.is_dir():
            continue
        for ext in (".dylib", ".so"):
            stub = sub_build / f"libdacestub_{stem}_{stem}{ext}"
            if stub.exists():
                candidates.append(stub)

    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


# ── Timing phase ───────────────────────────────────────────────────────────────
def run_dace_timing_phase(
    build_dir: pathlib.Path,
    out_path: pathlib.Path,
    pattern: str,
    reps: int,
    len_1d: int,
    src_root: "pathlib.Path | None" = None,
    debug_kernel: "str | None" = None,
) -> None:
    SIGNATURES = _load_signatures(src_root)
    if SIGNATURES is None:
        return

    is_float = bool(re.search(r"_f(_single)?\.py$", pattern))
    pool     = _make_array_pool(len_1d, is_float)
    rows: list[tuple] = []
    skipped = 0

    kernel_src_files: list[pathlib.Path] = []
    if src_root is not None and src_root.is_dir():
        kernel_src_files = list(src_root.glob("**/*.py"))

    kernel_dirs = sorted(
        d for d in build_dir.iterdir()
        if d.is_dir() and (d / "program.sdfgz").exists()
    )
    print(f"  [timing] Found {len(kernel_dirs)} compiled DaCe kernel folders")

    for kdir in kernel_dirs:
        stem = kdir.name
        base = re.sub(r"_(d|f)(_single)?$", "", stem)

        sig = None
        for candidate in [
            stem,
            re.sub(r"_(d|f)(_single)?$", "", stem),
            re.sub(r"_d_single$", "_single", stem),
            re.sub(r"_f_single$", "_single", stem),
            re.sub(r"_(double|float|single)$", "", stem),
        ]:
            sig = SIGNATURES.get(candidate)
            if sig is not None:
                base = candidate
                break

        if sig is None:
            available = sorted(SIGNATURES.keys())[:10]
            print(f"  [timing] SKIP {stem} — not in SIGNATURES. Sample keys: {available}")
            skipped += 1
            continue

        src_py = next(
            (p for p in kernel_src_files if p.stem == stem or p.stem == base), None
        )
        if src_py is not None:
            src_order = _sig_order_from_source(src_py, base)
            if src_order is not None:
                sig_by_name = {pname: (pname, ct_d, ct_f) for pname, ct_d, ct_f in sig}
                reordered  = [sig_by_name[p] for p in src_order if p in sig_by_name]
                reordered += [e for e in sig if e[0] not in {p for p in src_order}]
                sig = reordered

        dylib = _find_dylib(kdir, stem)
        if dylib is None:
            print(f"  [timing] SKIP {stem} — no .dylib/.so in {kdir / 'build'}")
            skipped += 1
            continue

        try:
            lib = ctypes.CDLL(str(dylib))
        except OSError as exc:
            print(f"  [timing] SKIP {stem} — cannot load {dylib.name}: {exc}")
            skipped += 1
            continue

        init_sym     = f"__dace_init_{stem}"
        exit_sym     = f"__dace_exit_{stem}"
        run_sym_name = f"__program_{stem}"
        if run_sym_name is None:
            print(f"  [timing] SKIP {stem} — run symbol not found")
            skipped += 1
            continue

        call_args, _keep = _build_dace_ctypes_args(sig, pool, is_float)
        if call_args is None:
            missing = [p for p, _, _ in sig if pool.get(p) is None]
            print(f"  [timing] SKIP {stem} — unresolved arg(s): {missing}")
            skipped += 1
            continue

        print(f"  [timing] running {stem} ...", end=" ", flush=True)

        # Resolve libomp path early so child_lines can reference it
        _conda_prefix = pathlib.Path(sys.executable).parent.parent
        _libomp = next((
            str(p) for p in [
                _conda_prefix / "lib" / "libomp.dylib",
                _conda_prefix / "lib" / "libiomp5.dylib",
                pathlib.Path("/opt/homebrew/opt/libomp/lib/libomp.dylib"),
                pathlib.Path("/opt/homebrew/lib/libomp.dylib"),
                pathlib.Path("/usr/local/lib/libomp.dylib"),
                _conda_prefix / "lib" / "libiomp5.so",
                _conda_prefix / "lib" / "libomp.so",
                pathlib.Path("/usr/lib/x86_64-linux-gnu/libomp.so.5"),
                pathlib.Path("/usr/lib/aarch64-linux-gnu/libomp.so.5"),
            ] if p.exists()
        ), None)

        # Serialise the *raw* numpy/scalar pool values (not ctypes objects).
        # The child process rebuilds ctypes args from scratch using the same helpers.
        dylib_str    = str(dylib)
        init_sym     = f"__dace_init_{stem}"
        exit_sym     = f"__dace_exit_{stem}"
        module_path  = str(pathlib.Path(__file__).resolve())

        # Extract only the pool keys this kernel needs, as plain numpy/scalars
        raw_pool = {}
        for pname, _, _ in sig:
            v = pool.get(pname)
            if v is not None:
                raw_pool[pname] = v

        # Serialise sig as (pname, dtype_name_d, dtype_name_f) so ctypes aren't pickled
        def _ctype_name(ct):
            return getattr(ct, "__name__", None) or repr(ct)
        sig_serial = [(pname, _ctype_name(ct_d), _ctype_name(ct_f)) for pname, ct_d, ct_f in sig]

        pool_b64   = base64.b64encode(pickle.dumps(raw_pool)).decode()
        sig_b64    = base64.b64encode(pickle.dumps(sig_serial)).decode()

        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        tmp_path = tmp.name

        child_lines = [
            # Preload libomp with RTLD_GLOBAL FIRST, before any other imports,
            # so OMP symbols are globally visible when the kernel .dylib loads.
            "import ctypes as _ctypes_early",
            "for _omp_path in [" + repr(str(_libomp)) + "]:",
            "    if _omp_path and _omp_path != 'None':",
            "        try: _ctypes_early.CDLL(_omp_path, mode=_ctypes_early.RTLD_GLOBAL)",
            "        except OSError: pass",
            "import ctypes, statistics, time as _t, json, pathlib, pickle, base64, sys, importlib.util",
            # Load the parent module so we can reuse _is_pointer_ctype, _array_to_ptr etc.
            "spec = importlib.util.spec_from_file_location('_cdace', " + repr(module_path) + ")",
            "mod  = importlib.util.module_from_spec(spec)",
            "spec.loader.exec_module(mod)",
            "import numpy as np",
            "raw_pool   = pickle.loads(base64.b64decode(" + repr(pool_b64) + "))",
            "sig_serial = pickle.loads(base64.b64decode(" + repr(sig_b64) + "))",
            "is_float   = " + repr(is_float),
            # Reconstruct sig with real ctypes
            "_CMAP = {",
            "    'LP_c_double': ctypes.POINTER(ctypes.c_double),",
            "    'LP_c_float':  ctypes.POINTER(ctypes.c_float),",
            "    'LP_c_int':    ctypes.POINTER(ctypes.c_int),",
            "    'LP_c_long':   ctypes.POINTER(ctypes.c_int64),",
            "    'LP_c_int64':  ctypes.POINTER(ctypes.c_int64),",
            "    'LP_c_longlong': ctypes.POINTER(ctypes.c_int64),",
            "    'c_double': ctypes.c_double,",
            "    'c_float':  ctypes.c_float,",
            "    'c_int':    ctypes.c_int,",
            "    'c_int64':  ctypes.c_int64,",
            "    'c_long':   ctypes.c_int64,",
            "    'c_int32':  ctypes.c_int32,",
            "}",
            "sig = [(pn, _CMAP.get(cdn, ctypes.c_int64), _CMAP.get(cfn, ctypes.c_int64))",
            "       for pn, cdn, cfn in sig_serial]",
            "call_args, keep = mod._build_dace_ctypes_args(sig, raw_pool, is_float)",
            "if call_args is None:",
            "    raise RuntimeError('missing pool args in child')",
            # Load library and run
            "lib = ctypes.CDLL(" + repr(dylib_str) + ")",
            "fn_init = getattr(lib, " + repr(init_sym) + ")",
            "fn_run  = getattr(lib, " + repr(run_sym_name) + ")",
            "fn_exit = getattr(lib, " + repr(exit_sym) + ")",
            "fn_init.restype = ctypes.c_void_p",
            "fn_run.restype  = None",
            "fn_exit.restype = None",
            "print('[child] sig:', [(p, cd, cf) for p,cd,cf in sig_serial])",
            "print('[child] pool keys:', list(raw_pool.keys()))",
            "print('[child] call_args types:', [type(a).__name__ for a in call_args])",
            "import sys as _sys; _sys.stdout.flush()",
            "handle = fn_init()",
            "h = ctypes.c_void_p(handle)",
            "timings = []",
            "for _ in range(" + str(reps) + "):",
            "    t0 = _t.perf_counter_ns()",
            "    fn_run(h, *call_args)",
            "    timings.append(_t.perf_counter_ns() - t0)",
            "fn_exit(h)",
            "result = dict(median=statistics.median(timings), min=min(timings),",
            "              stdev=statistics.stdev(timings) if " + str(reps) + ">1 else 0.0)",
            "pathlib.Path(" + repr(tmp_path) + ").write_text(json.dumps(result))",
        ]
        child_script = "\n".join(child_lines)

        # Write child script to a temp file — avoids OSError "Argument list too long"
        # when base64-encoded pool data makes the -c string exceed OS limits.
        tmp_script = tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False)
        tmp_script.write(child_script)
        tmp_script.close()

        child_env = {**os.environ, "OMP_NUM_THREADS": "1", "KMP_DUPLICATE_LIB_OK": "TRUE"}
        # DYLD_INSERT_LIBRARIES (macOS) / LD_PRELOAD (Linux) — best effort only
        if _libomp:
            if sys.platform == "darwin":
                child_env.setdefault("DYLD_INSERT_LIBRARIES", _libomp)
            else:
                child_env.setdefault("LD_PRELOAD", _libomp)

        # --debug-kernel: save script to /tmp for manual inspection and skip running
        if debug_kernel and (stem == debug_kernel or base == debug_kernel):
            debug_path = f"/tmp/dace_debug_{stem}.py"
            pathlib.Path(debug_path).write_text(child_script)
            print(f"\n  [debug] Child script saved to: {debug_path}")
            print(f"  [debug] Run manually with:")
            print(f"  [debug]   python3 {debug_path}")
            print(f"  [debug] Or for crash details:")
            print(f"  [debug]   OMP_NUM_THREADS=1 KMP_DUPLICATE_LIB_OK=TRUE python3 {debug_path}")
            skipped += 1
            continue

        proc = subprocess.run(
            [sys.executable, tmp_script.name],
            timeout=60,
            capture_output=True,
            text=True,
            env=child_env,
        )
        try:
            pathlib.Path(tmp_script.name).unlink(missing_ok=True)
        except Exception:
            pass

        if proc.returncode != 0:
            err_lines = (proc.stderr or proc.stdout or "").strip().splitlines()
            err_tail  = " | ".join(err_lines[-3:]) if err_lines else ""
            print(f"CRASH (exit {proc.returncode}){(': ' + err_tail) if err_tail else ''}", flush=True)
            skipped += 1
        else:
            try:
                result = json.loads(pathlib.Path(tmp_path).read_text())
                print("ok", flush=True)
                rows.append((base, result["median"], result["min"], result["stdev"]))
            except Exception as exc:
                print(f"failed reading result: {exc}", flush=True)
                skipped += 1

        try:
            pathlib.Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass
        del _keep

    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["kernel,median_ns,min_ns,stdev_ns"]
    for kernel, med, mn, std in sorted(rows):
        lines.append(f"{kernel},{med:.0f},{mn:.0f},{std:.0f}")
    out_path.write_text("\n".join(lines) + "\n")
    print(f"  [timing] {len(rows)} kernels timed, {skipped} skipped -> {out_path}")


# ── Compilation helpers ────────────────────────────────────────────────────────
def _compile_one(args_tuple):
    py_file, build_dir, force = args_tuple
    stem      = py_file.stem
    kdir      = build_dir / stem
    sdfg_path = kdir / "program.sdfgz"

    if sdfg_path.exists() and not force:
        return stem, True, "cached"

    kdir.mkdir(parents=True, exist_ok=True)
    script_lines = [
        "import sys, pathlib, dace, importlib.util",
        "kdir = pathlib.Path(" + repr(str(kdir)) + ")",
        "kdir.mkdir(parents=True, exist_ok=True)",
        "dace.config.Config.set('default_build_folder', value=str(kdir / 'build'))",
        "spec = importlib.util.spec_from_file_location(" + repr(stem) + ", " + repr(str(py_file)) + ")",
        "mod  = importlib.util.module_from_spec(spec)",
        "spec.loader.exec_module(mod)",
        "prog = next(",
        "    (getattr(mod, a) for a in dir(mod)",
        "     if not a.startswith('_') and hasattr(getattr(mod, a, None), 'to_sdfg')),",
        "    None,",
        ")",
        "if prog is None:",
        "    raise RuntimeError('no @dace.program found')",
        "sdfg = prog.to_sdfg()",
        "sdfg.save(str(kdir / 'program.sdfgz'))",
        "sdfg.compile()",
    ]
    try:
        result = subprocess.run(
            [sys.executable, "-c", "\n".join(script_lines)],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout).strip().splitlines()
            return stem, False, err[-1] if err else "unknown error"
        return stem, True, "compiled"
    except subprocess.TimeoutExpired:
        return stem, False, "timeout"
    except Exception as exc:
        return stem, False, str(exc)


# ── Public API ─────────────────────────────────────────────────────────────────
def compile_dace_all(
    src_root: "str | pathlib.Path",
    build_dir: "str | pathlib.Path",
    pattern: str = "*.py",
    force: bool = False,
    jobs: int = 0,
) -> dict:
    src_root  = pathlib.Path(src_root).resolve()
    build_dir = pathlib.Path(build_dir).resolve()
    j = jobs if jobs > 0 else multiprocessing.cpu_count()
    all_py = sorted(src_root.glob("**/*.py"))
    kernel_files = [
        f for f in all_py
        if fnmatch.fnmatch(f.name, pattern) and not f.name.startswith("_")
    ]
    work = [(f, build_dir, force) for f in kernel_files]
    if j == 1:
        results = [_compile_one(item) for item in work]
    else:
        with multiprocessing.Pool(processes=j) as pool:
            results = pool.map(_compile_one, work)
    ok  = [stem for stem, s, _ in results if s]
    err = {stem: msg for stem, s, msg in results if not s}
    return {"compiled": ok, "failed": err, "total": len(kernel_files)}


def parse_dace_vec_reports(build_dir: "str | pathlib.Path") -> dict:
    build_dir = pathlib.Path(build_dir)
    reports: dict[str, str] = {}
    for rpt in build_dir.rglob("vec_report.txt"):
        reports[rpt.parent.name] = rpt.read_text()
    return reports


# ── Main ───────────────────────────────────────────────────────────────────────
def main_compile_dace(
    default_root: str = "tsvc_2/tsvc_dace_microkernels",
    default_build_dir: str = ".dace_build",
    argv: "list | None" = None,
) -> int:
    ap = argparse.ArgumentParser(description="Compile (and optionally time) DaCe TSVC kernel files.")
    ap.add_argument("root", metavar="SRC_ROOT")
    ap.add_argument("-b", "--build-dir", default=default_build_dir, metavar="DIR")
    ap.add_argument("--pattern", default="*.py", metavar="GLOB")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--time", action="store_true")
    ap.add_argument("--reps", type=int, default=30, metavar="N")
    ap.add_argument("--len-1d", type=int, default=1024, metavar="N", dest="len_1d")
    ap.add_argument("-j", type=int, default=multiprocessing.cpu_count(), metavar="N")
    ap.add_argument(
        "--debug-kernel", default=None, metavar="STEM",
        help="Save child timing script for STEM to /tmp/dace_debug_<STEM>.py and exit (for crash diagnosis)."
    )
    ap.add_argument(
        "--timing-out", default=None, metavar="FILE",
        help="Write timing CSV to FILE (default: <build_dir>/dace.timing_report.csv)."
    )
    ap.add_argument(
        "--vec-report", action="store_true",
        help="Parse *.rpt vectorization-remark files from the build dir and print a summary."
    )
    ap.add_argument(
        "--vec-report-out", default=None, metavar="FILE",
        help="Write vec-report summary to FILE (default: <build_dir>/dace.vec_report.txt)."
    )
    args = ap.parse_args(argv)

    src_root  = pathlib.Path(args.root).resolve()
    build_dir = pathlib.Path(args.build_dir).resolve()

    if not src_root.is_dir():
        raise SystemExit(f"ERROR: source root not found: {src_root}")

    all_py = sorted(src_root.glob("**/*.py"))
    kernel_files = [
        f for f in all_py
        if fnmatch.fnmatch(f.name, args.pattern) and not f.name.startswith("_")
    ]
    print(f"Found {len(kernel_files)} DaCe kernel files under {src_root}")

    t0 = _time.perf_counter()
    work = [(f, build_dir, args.force) for f in kernel_files]
    if args.j == 1:
        results = [_compile_one(item) for item in work]
    else:
        with multiprocessing.Pool(processes=args.j) as pool:
            results = pool.map(_compile_one, work)

    ok  = sum(1 for _, s, _ in results if s)
    err = sum(1 for _, s, _ in results if not s)
    for stem, success, msg in results:
        if not success:
            print(f"  [compile] FAIL {stem}: {msg}")
    print(f"Compiled {ok}/{len(kernel_files)} kernels{f' ({err} failed)' if err else ''} in {_time.perf_counter()-t0:.1f}s")

    if args.time:
        timing_out = (
            pathlib.Path(args.timing_out) if args.timing_out
            else build_dir / "dace.timing_report.csv"
        )
        print(f"Running DaCe timing phase ({args.reps} reps, len_1d={args.len_1d}) ...")
        t1 = _time.perf_counter()
        run_dace_timing_phase(
            build_dir=build_dir,
            out_path=timing_out,
            pattern=args.pattern,
            reps=args.reps,
            len_1d=args.len_1d,
            src_root=src_root,
            debug_kernel=args.debug_kernel,
        )
        print(f"Done in {_time.perf_counter()-t1:.1f}s")

    return 0


if __name__ == "__main__":
    raise SystemExit(main_compile_dace())