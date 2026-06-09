"""Python bindings for ``libtsvc_extensions_kernels.so``.

Sibling of ``tsvc_2/tsvc_bindings.py`` -- same wrapper architecture
(SIGNATURES table, ``_KernelWrapper``, ``__getattr__`` dispatch),
re-pointed at the extension corpus's split+compile pipeline.

The corpus C++ file declares one ``<name>_run_timed`` per kernel, each
split into a ``<name>_d`` and ``<name>_f`` variant; this module wires
them as Python callables that take numpy arrays + scalars and return the
per-call elapsed time in nanoseconds.

Usage::

    from tsvc_2_5.tsvc_2_5_bindings import (
        ExtensionLibrary,
    )

    lib = ExtensionLibrary()  # auto-builds if .so is missing
    ns  = lib.ext_strided_load_ssym_d(dst, src, scale=1.5,
                                      len_1d=1024, ssym=3)
    ns  = lib.s121_sym_k_d(a, b, len_1d=1024, k=4)

    lib.list_kernels()  # ['ext_floordiv_offset_d', 'ext_floordiv_offset_f', ...]
"""

import ctypes
import numpy as np
import os
import pathlib
from typing import Optional

# ── ctypes shorthands ──
_dp = ctypes.POINTER(ctypes.c_double)
_fp = ctypes.POINTER(ctypes.c_float)
_i64p = ctypes.POINTER(ctypes.c_int64)
_int = ctypes.c_int
_dbl = ctypes.c_double
_flt = ctypes.c_float

# ── Signature registry ─────────────────────────────────────────────────
# Each entry: kernel_base_name -> list of (param_name, ctype_for_d,
# ctype_for_f). ``time_ns`` is appended automatically and is not listed.
#
# 'A'  = mutable array  (double*/float*)
# 'CA' = const array    (semantically; ctype matches A)
# 'I'  = c_int scalar
# 'D'  = double/float scalar
# 'I64A' = const int64* array (used for ``idx`` / ``ip``)


def _A(name):
    return (name, _dp, _fp)


def _CA(name):
    return (name, _dp, _fp)


def _I(name):
    return (name, _int, _int)


def _D(name):
    return (name, _dbl, _flt)


def _I64A(name):
    return (name, _i64p, _i64p)


# fmt: off
SIGNATURES = {
    # %A  Symbolic-stride load (gather)
    "ext_strided_load_ssym":   [_A("dst"), _CA("src"), _D("scale"), _I("len_1d"), _I("ssym")],
    "ext_strided_load_2":      [_A("dst"), _CA("src"), _D("scale"), _I("len_1d")],

    # %B  Symbolic-stride store (scatter)
    "ext_strided_store_ssym":  [_A("dst"), _CA("src"), _D("scale"), _I("len_1d"), _I("ssym")],
    "ext_strided_store_2":     [_A("dst"), _CA("src"), _D("scale"), _I("len_1d")],

    # %C  Indirect gather / scatter
    "ext_gather_load":         [_A("dst"), _CA("src"), _I64A("idx"), _D("scale"), _I("len_1d")],
    "ext_scatter_store":       [_A("dst"), _CA("src"), _I64A("idx"), _D("scale"), _I("len_1d")],

    # %D  Quasi-affine offsets (floor-div / modulo)
    "ext_floordiv_offset":     [_A("a"), _CA("b"), _I("len_1d")],
    "ext_floordiv_offset_m":   [_A("a"), _CA("b"), _I("len_1d"), _I("m")],
    "ext_modular_wrap":        [_A("a"), _CA("b"), _I("len_1d"), _I("k")],

    # %E  WAR (write-after-read) families
    "ext_war_unit":            [_A("a"), _CA("b"), _I("len_1d")],
    "ext_war_sym":             [_A("a"), _CA("b"), _I("len_1d"), _I("k")],

    # %F  Multi-front conflict peel
    "ext_peel_multi_back":     [_A("a"), _CA("b"), _I("len_1d")],

    # %G  2D tile with symbolic tile size
    "ext_tile_2d_sym":         [_A("b"), _CA("a"), _I("len_2d"), _I("s")],

    # %H  TSVC-named symbolic variants
    "s121_sym_k":              [_A("a"), _CA("b"), _I("len_1d"), _I("k")],
    "s4113_ssym":              [_A("a"), _CA("b"), _CA("c"), _I64A("ip"), _I("len_1d"), _I("ssym")],
    "vas_ssym":                [_A("a"), _CA("b"), _I64A("ip"), _I("len_1d"), _I("ssym")],

    # %I  Loop-fission family
    "fission_indep_2body":     [_A("a"), _A("b"), _CA("x"), _CA("y"), _CA("z"), _I("len_1d")],
    "fission_dep_then_indep":  [_A("a"), _A("b"), _CA("x"), _CA("y"), _I("len_1d")],
    "fission_dep_const_offset":[_A("a"), _A("b"), _CA("x"), _CA("y"), _CA("z"), _I("len_1d")],
    "fission_dep_sym_offset":  [_A("a"), _A("b"), _CA("x"), _CA("y"), _CA("z"), _I("len_1d"), _I("k")],

    # %J  Already-tiled stencils (constant + symbolic tile sizes)
    "jacobi2d_tiled_const":        [_A("b"), _CA("a"), _I("len_2d")],
    "jacobi2d_tiled_sym":          [_A("b"), _CA("a"), _I("len_2d"), _I("t")],
    "jacobi2d_double_tiled_const": [_A("b"), _CA("a"), _I("len_2d")],
    "jacobi2d_double_tiled_sym":   [_A("b"), _CA("a"), _I("len_2d"), _I("t1"), _I("t2")],
    "heat3d_tiled_const":          [_A("b"), _CA("a"), _I("len_3d")],
    "heat3d_tiled_sym":            [_A("b"), _CA("a"), _I("len_3d"), _I("t")],

    # %K  ECRAD-style clamped reduction
    "ecrad_clamped_reduction": [_A("out"), _CA("x"), _CA("y"), _CA("d"), _I("len_1d")],

    # %L  Conditional masked stores
    "masked_store_const":      [_A("a"), _CA("b"), _I64A("mask"), _I("len_1d")],
    "masked_store_sym":        [_A("a"), _CA("b"), _CA("threshold_data"), _I("len_1d"), _D("k")],

    # %M  Quasi-affine subscript ranges
    "quasi_affine_reduce_even":         [_CA("a"), _A("out"), _I("len_1d")],
    "quasi_affine_reduce_odd":          [_CA("a"), _A("out"), _I("len_1d")],
    "quasi_affine_pairwise_sum":        [_CA("a"), _A("b"), _I("len_1d")],
    "quasi_affine_mod_k_stripe":        [_A("a"), _CA("b"), _CA("c"), _I("len_1d"), _I("k")],
    "quasi_affine_floor_div_scatter":   [_CA("a"), _A("b"), _I("len_1d")],

    # %N  Wavefront / loop-skew
    "wavefront2d":             [_A("a"), _I("len_2d")],

    # %O  Early-exit / find-first (break loops)
    "ext_break_find_first":    [_A("a"), _CA("b"), _CA("c"), _CA("d"), _I("len_1d")],
    "ext_break_post_body":     [_A("a"), _CA("b"), _CA("c"), _I("len_1d")],
    "ext_break_capture":       [_CA("a"), _I64A("out_index"), _A("out_value"), _I("len_1d"), _D("k")],

    # %P  Conditional reduction
    "cond_reduce_sum":         [_CA("a"), _A("out"), _I("len_1d")],
    "cond_reduce_sym":         [_CA("a"), _A("out"), _I("len_1d"), _D("k")],

    # %Q  Induction-variable closed form
    "iv_additive":             [_A("out"), _I("len_1d")],
    "iv_multiplicative":       [_A("out"), _I("len_1d")],

    # %R  Argmax / argmin value
    "argmax_value":            [_CA("a"), _A("out"), _I("len_1d")],
    "argmin_value":            [_CA("a"), _A("out"), _I("len_1d")],

    # %S  Negative stride + manual unroll
    "neg_stride_rev":          [_A("a"), _CA("b"), _I("len_1d")],
    "reroll_saxpy7":           [_A("a"), _CA("b"), _I("len_1d")],

    # %T  Strided / multiple scans
    "scan_strided_2":          [_A("a"), _CA("x"), _I("len_1d")],
    "scan_strided_sym":        [_A("a"), _CA("x"), _I("len_1d"), _I("k")],
    "scan_multi_carry":        [_A("a"), _A("b"), _CA("x"), _CA("y"), _I("len_1d")],

    # %U  Canonicalize unit-test gap kernels
    "scan_conditional":        [_A("out"), _CA("delta"), _I64A("mask"), _I("len_1d")],
    "scan_multi_5carry":       [_A("acc"), _CA("delta"), _I("len_1d")],
    "argmax_with_index":       [_CA("a"), _A("out_value"), _I64A("out_index"), _I("len_1d")],
    "reroll_gather":           [_A("a"), _CA("b"), _I64A("ip"), _I("len_1d")],
    "thomas_solve":            [_CA("a"), _CA("b"), _A("c"), _A("d"), _A("x"), _I("len_1d")],
    "reduce_inner_carry":      [_CA("a"), _A("out"), _I("len_2d")],
    "config_select_branch":    [_A("out_a"), _A("out_b"), _CA("src"), _I("len_1d"), _I("k")],
    "move_if_data_dep_nest":   [_A("out"), _CA("src"), _CA("cond"), _I("len_2d")],
    "fuse_move_ifs":           [_A("a"), _A("b"), _CA("src"), _CA("cond"), _I("len_2d"), _I("k")],
}
# fmt: on


def _to_carg(val, ctype_d, is_float):
    """Convert a Python/numpy value to the appropriate ctypes
    argument, casting float arrays between fp64/fp32 if needed."""
    if isinstance(val, np.ndarray):
        if ctype_d is _i64p:
            return val.astype(np.int64, copy=False).ctypes.data_as(_i64p)
        if is_float and val.dtype == np.float64:
            val = val.astype(np.float32)
        elif not is_float and val.dtype == np.float32:
            val = val.astype(np.float64)
        if is_float:
            return val.ctypes.data_as(_fp)
        return val.ctypes.data_as(_dp)
    if ctype_d is _int:
        return _int(int(val))
    if ctype_d is _dbl:
        return (_flt if is_float else _dbl)(float(val))
    return val


class _KernelWrapper:
    """Callable wrapper around a single kernel variant."""

    __slots__ = ("_func", "_sig", "_is_float", "_name")

    def __init__(self, func, sig, is_float, name):
        self._func = func
        self._sig = sig
        self._is_float = is_float
        self._name = name

    def __call__(self, *args, **kwargs):
        sig = self._sig
        if len(args) + len(kwargs) != len(sig):
            param_names = [s[0] for s in sig]
            raise TypeError(f"{self._name}() expects {len(sig)} args {param_names}, "
                            f"got {len(args)} positional + {len(kwargs)} keyword")

        cargs = []
        for i, (pname, ctype_d, _ctype_f) in enumerate(sig):
            if i < len(args):
                val = args[i]
            elif pname in kwargs:
                val = kwargs[pname]
            else:
                raise TypeError(f"{self._name}(): missing argument '{pname}'")
            cargs.append(_to_carg(val, ctype_d, self._is_float))

        time_ns = np.zeros(1, dtype=np.int64)
        cargs.append(time_ns.ctypes.data_as(_i64p))

        self._func(*cargs)
        return int(time_ns[0])

    def __repr__(self):
        params = ", ".join(s[0] for s in self._sig)
        return f"<kernel {self._name}({params}) -> ns>"


class ExtensionLibrary:
    """Load ``libtsvc_extensions_kernels.so`` and expose every kernel
    as a typed callable.

    If the ``.so`` does not exist, the split + compile pipeline runs
    automatically:

    1. ``split_cpp_kernels.py`` splits the monolithic core into
       per-kernel sources under ``tsvc_2_5_cpp_microkernels/``;
    2. ``compile_cpp_kernels.py`` compiles every ``.o`` and links into
       a single ``.so``.

    Parameters
    ----------
    so_path : str | Path, optional
        Path to the shared library
        (default: ``.tsvc_ext_build/libtsvc_extensions_kernels.so``).
    kernel_root : str | Path, optional
        Directory containing per-kernel ``.cpp`` files
        (default: ``tsvc_2_5/tsvc_2_5_cpp_microkernels``).
    core_cpp : str | Path, optional
        Path to the monolithic C++ source used when auto-splitting
        (default: ``tsvc_2_5/tsvc_2_5_core.cpp``).
    build_dir : str | Path, optional
        Build directory for ``.o`` and ``.so`` files
        (default: ``.tsvc_ext_build``).
    jobs : int, optional
        Parallel compile jobs for auto-build (default: ``os.cpu_count()``).
    """

    def __init__(
        self,
        so_path: "str | pathlib.Path" = ".tsvc_ext_build/libtsvc_extensions_kernels.so",
        kernel_root: "str | pathlib.Path" = "tsvc_2_5/tsvc_2_5_cpp_microkernels",
        core_cpp: "str | pathlib.Path" = "tsvc_2_5/tsvc_2_5_core.cpp",
        build_dir: "str | pathlib.Path" = ".tsvc_ext_build",
        jobs: Optional[int] = None,
    ):
        so_path = pathlib.Path(so_path)

        if not so_path.exists():
            self._auto_build(so_path, kernel_root, core_cpp, build_dir, jobs)

        self._lib = ctypes.CDLL(str(so_path))
        self._kernels: "dict[str, _KernelWrapper]" = {}

        for base, sig in SIGNATURES.items():
            for suffix, is_float in [("_d", False), ("_f", True)]:
                name = f"{base}{suffix}"
                try:
                    func = getattr(self._lib, name)
                except AttributeError:
                    continue

                argtypes = []
                for _, ctype_d, ctype_f in sig:
                    argtypes.append(ctype_f if is_float else ctype_d)
                argtypes.append(_i64p)
                func.argtypes = argtypes
                func.restype = None

                self._kernels[name] = _KernelWrapper(func, sig, is_float, name)

    @staticmethod
    def _auto_build(so_path, kernel_root, core_cpp, build_dir, jobs):
        kernel_root = pathlib.Path(kernel_root)
        core_cpp = pathlib.Path(core_cpp)
        build_dir = pathlib.Path(build_dir)
        if jobs is None:
            jobs = os.cpu_count() or 1

        if not kernel_root.exists() or not any(kernel_root.rglob("*.cpp")):
            if not core_cpp.exists():
                raise FileNotFoundError(f"Cannot auto-build: {core_cpp} not found. "
                                        f"Either provide the monolithic source or pre-split kernels in {kernel_root}/.")
            print(f"Splitting {core_cpp} -> {kernel_root}/ ...")
            from tsvc_2_5.split_cpp_kernels import main as split_main
            import sys
            old_argv = sys.argv
            sys.argv = ["split_cpp_kernels", "-i", str(core_cpp), "-o", str(kernel_root)]
            try:
                split_main()
            finally:
                sys.argv = old_argv

        print(f"Compiling {kernel_root}/ -> {so_path} (-j{jobs}) ...")
        from tsvc_2_5.compile_cpp_kernels import compile_library
        compile_library(
            root=str(kernel_root),
            build_dir=str(build_dir),
            so_name=so_path.name,
            jobs=jobs,
        )

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._kernels[name]
        except KeyError:
            raise AttributeError(f"No kernel '{name}' found in library")

    def list_kernels(self) -> "list[str]":
        """Return a sorted list of available ``<kernel>_d`` /
        ``<kernel>_f`` names."""
        return sorted(self._kernels.keys())

    def __repr__(self):
        return f"<ExtensionLibrary: {len(self._kernels)} kernels>"
