"""
Python bindings for libtsvc_kernels.so.

If the shared library does not exist, the split and compile pipeline is
invoked automatically (requires tsvc2_core.cpp in the kernel root directory).

Usage:
    from tsvc_bindings import TSVCLibrary

    # Auto-builds if .so is missing
    lib = TSVCLibrary()

    # Call a kernel — pass numpy arrays and scalars, get elapsed ns back
    ns = lib.s000_d(a, b, iterations=100, len_1d=1024)
    ns = lib.s000_f(a, b, iterations=100, len_1d=1024)

    # Reduction — result written to length-1 array
    result = np.zeros(1)
    ns = lib.s314_d(a, result, iterations=100, len_1d=1024)
    print(result[0])  # max value

    # List available kernels
    lib.list_kernels()
"""

import ctypes
import ctypes.util
import numpy as np
import os
import pathlib
from typing import Optional

# ── ctypes shorthands ──
_dp = ctypes.POINTER(ctypes.c_double)       # double *
_fp = ctypes.POINTER(ctypes.c_float)        # float *
_ip = ctypes.POINTER(ctypes.c_int)          # int *
_i64p = ctypes.POINTER(ctypes.c_int64)      # int64_t *
_int = ctypes.c_int
_dbl = ctypes.c_double
_flt = ctypes.c_float
_i32 = ctypes.c_int


# ── Signature registry ──
# Each entry: kernel_base_name -> list of (param_name, ctype_for_d, ctype_for_f)
# time_ns is appended automatically and not listed here.
# 'dp'=double ptr, 'fp'=float ptr, 'int'=c_int, 'dbl'=c_double, 'ip'=int ptr

def _A(name):
    """Array param: double* for _d, float* for _f."""
    return (name, _dp, _fp)

def _CA(name):
    """Const array param: same types, just semantic."""
    return (name, _dp, _fp)

def _IA(name):
    """Int array param (same for both variants)."""
    return (name, _ip, _ip)

def _I(name):
    """Int scalar."""
    return (name, _int, _int)

def _D(name):
    """Double/float scalar."""
    return (name, _dbl, _flt)

def _R(name):
    """Result array: double*/float* length-1 output."""
    return (name, _dp, _fp)


# fmt: off
SIGNATURES = {
    "s000":   [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "s111":   [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "s1111":  [_A("a"), _CA("b"), _CA("c"), _CA("d"), _I("iterations"), _I("len_1d")],
    "s112":   [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "s1112":  [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "s113":   [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "s1113":  [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "s114":   [_A("aa"), _CA("bb"), _I("iterations"), _I("len_2d"), _I("vlen")],
    "s115":   [_A("a"), _CA("aa"), _I("iterations"), _I("len_2d")],
    "s1115":  [_A("aa"), _CA("bb"), _CA("cc"), _I("iterations"), _I("len_2d")],
    "s116":   [_A("a"), _I("iterations"), _I("len_1d")],
    "s118":   [_A("a"), _CA("bb"), _I("iterations"), _I("len_2d")],
    "s119":   [_A("aa"), _CA("bb"), _I("iterations"), _I("len_2d")],
    "s1119":  [_A("aa"), _CA("bb"), _I("iterations"), _I("len_2d")],
    "s121":   [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "s122":   [_A("a"), _CA("b"), _I("iterations"), _I("len_1d"), _I("n1"), _I("n3")],
    "s123":   [_A("a"), _CA("b"), _CA("c"), _CA("d"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s124":   [_A("a"), _CA("b"), _CA("c"), _CA("d"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s125":   [_CA("aa"), _CA("bb"), _CA("cc"), _A("flat_2d_array"), _I("iterations"), _I("len_2d")],
    "s126":   [_A("bb"), _CA("cc"), _CA("flat_2d_array"), _I("iterations"), _I("len_2d")],
    "s127":   [_A("a"), _CA("b"), _CA("c"), _CA("d"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s128":   [_A("a"), _A("b"), _CA("c"), _CA("d"), _I("iterations"), _I("len_1d")],
    "s131":   [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "s132":   [_A("aa"), _CA("b"), _CA("c"), _I("iterations"), _I("len_2d")],
    "s141":   [_CA("bb"), _A("flat_2d_array"), _I("iterations"), _I("len_2d")],
    "s151":   [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "s152":   [_A("a"), _A("b"), _CA("c"), _CA("d"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s161":   [_A("a"), _CA("b"), _A("c"), _CA("d"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s1161":  [_A("a"), _A("b"), _A("c"), _CA("d"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s162":   [_A("a"), _CA("b"), _CA("c"), _I("iterations"), _I("k"), _I("len_1d")],
    "s171":   [_A("a"), _CA("b"), _I("inc"), _I("iterations"), _I("len_1d")],
    "s172":   [_A("a"), _CA("b"), _I("iterations"), _I("len_1d"), _I("n1"), _I("n3")],
    "s173":   [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "s174":   [_A("a"), _CA("b"), _I("iterations"), _I("len_1d"), _I("M")],
    "s175":   [_A("a"), _CA("b"), _I("inc"), _I("iterations"), _I("len_1d")],
    "s176":   [_A("a"), _CA("b"), _CA("c"), _I("iterations"), _I("len_1d")],
    "s211":   [_A("a"), _A("b"), _CA("c"), _CA("d"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s212":   [_A("a"), _A("b"), _CA("c"), _CA("d"), _I("iterations"), _I("len_1d")],
    "s1213":  [_A("a"), _A("b"), _CA("c"), _CA("d"), _I("iterations"), _I("len_1d")],
    "s221":   [_A("a"), _A("b"), _CA("c"), _CA("d"), _I("iterations"), _I("len_1d")],
    "s1221":  [_A("a"), _A("b"), _I("iterations"), _I("len_1d")],
    "s222":   [_A("a"), _A("b"), _CA("c"), _A("e"), _I("iterations"), _I("len_1d")],
    "s231":   [_A("aa"), _CA("bb"), _I("iterations"), _I("len_2d")],
    "s232":   [_A("aa"), _CA("bb"), _I("iterations"), _I("len_2d")],
    "s1232":  [_A("aa"), _CA("bb"), _CA("cc"), _I("iterations"), _I("len_2d"), _I("vlen")],
    "s233":   [_A("aa"), _A("bb"), _CA("cc"), _I("iterations"), _I("len_2d")],
    "s2233":  [_A("aa"), _A("bb"), _CA("cc"), _I("iterations"), _I("len_2d")],
    "s235":   [_A("a"), _A("aa"), _CA("b"), _CA("bb"), _CA("c"), _I("iterations"), _I("len_2d")],
    "s241":   [_A("a"), _A("b"), _CA("c"), _CA("d"), _I("iterations"), _I("len_1d")],
    "s242":   [_A("a"), _CA("b"), _CA("c"), _CA("d"), _I("iterations"), _I("len_1d"), _D("s1"), _D("s2")],
    "s243":   [_A("a"), _A("b"), _CA("c"), _CA("d"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s244":   [_A("a"), _A("b"), _CA("c"), _CA("d"), _I("iterations"), _I("len_1d")],
    "s1244":  [_A("a"), _CA("b"), _CA("c"), _A("d"), _I("iterations"), _I("len_1d")],
    "s2244":  [_A("a"), _CA("b"), _CA("c"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s251":   [_A("a"), _CA("b"), _CA("c"), _CA("d"), _I("iterations"), _I("len_1d")],
    "s1251":  [_A("a"), _A("b"), _CA("c"), _CA("d"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s2251":  [_A("a"), _A("b"), _CA("c"), _CA("d"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s3251":  [_A("a"), _A("b"), _CA("c"), _A("d"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s252":   [_A("a"), _CA("b"), _CA("c"), _I("iterations"), _I("len_1d")],
    "s253":   [_A("a"), _A("b"), _A("c"), _CA("d"), _I("iterations"), _I("len_1d")],
    "s254":   [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "s255":   [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "s256":   [_A("a"), _A("aa"), _CA("bb"), _CA("d"), _I("iterations"), _I("len_2d")],
    "s257":   [_A("a"), _A("aa"), _CA("bb"), _I("iterations"), _I("len_2d")],
    "s258":   [_A("a"), _CA("aa"), _A("b"), _CA("c"), _CA("d"), _A("e"), _I("iterations"), _I("len_2d")],
    "s261":   [_A("a"), _A("b"), _A("c"), _CA("d"), _I("iterations"), _I("len_1d")],
    "s271":   [_A("a"), _CA("b"), _CA("c"), _I("iterations"), _I("len_1d")],
    "s272":   [_A("a"), _A("b"), _CA("c"), _CA("d"), _CA("e"), _I("iterations"), _I("len_1d"), _I("threshold")],
    "s273":   [_A("a"), _A("b"), _A("c"), _CA("d"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s274":   [_A("a"), _A("b"), _CA("c"), _CA("d"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s275":   [_A("aa"), _CA("bb"), _CA("cc"), _I("iterations"), _I("len_2d")],
    "s2275":  [_A("a"), _A("aa"), _CA("b"), _CA("bb"), _CA("c"), _CA("cc"), _CA("d"), _I("iterations"), _I("len_2d")],
    "s276":   [_A("a"), _CA("b"), _CA("c"), _CA("d"), _I("iterations"), _I("len_1d")],
    "s277":   [_A("a"), _A("b"), _CA("c"), _CA("d"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s278":   [_A("a"), _A("b"), _A("c"), _CA("d"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s279":   [_A("a"), _A("b"), _A("c"), _CA("d"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s1279":  [_CA("a"), _CA("b"), _A("c"), _CA("d"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s2710":  [_A("a"), _A("b"), _A("c"), _CA("d"), _CA("e"), _CA("x"), _I("iterations"), _I("len_1d")],
    "s2711":  [_A("a"), _CA("b"), _CA("c"), _I("iterations"), _I("len_1d")],
    "s2712":  [_A("a"), _CA("b"), _CA("c"), _I("iterations"), _I("len_1d")],
    "s281":   [_A("a"), _A("b"), _CA("c"), _I("iterations"), _I("len_1d")],
    "s1281":  [_A("a"), _A("b"), _CA("c"), _CA("d"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s291":   [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "s292":   [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "s293":   [_A("a"), _I("iterations"), _I("len_1d")],
    "s2101":  [_A("aa"), _CA("bb"), _CA("cc"), _I("iterations"), _I("len_2d")],
    "s2102":  [_A("aa"), _I("iterations"), _I("len_2d")],
    "s2111":  [_A("aa"), _I("iterations"), _I("len_2d")],
    "s311":   [_A("a"), _R("sum_out"), _I("iterations"), _I("len_1d")],
    "s31111": [_A("a"), _A("b"), _I("iterations"), _I("len_1d")],
    "s312":   [_A("a"), _R("result"), _I("iterations"), _I("len_1d")],
    "s313":   [_CA("a"), _CA("b"), _R("dot"), _I("iterations"), _I("len_1d")],
    "s314":   [_CA("a"), _R("result"), _I("iterations"), _I("len_1d")],
    "s315":   [_A("a"), _R("result"), _I("iterations"), _I("len_1d")],
    "s316":   [_CA("a"), _R("result"), _I("iterations"), _I("len_1d")],
    "s317":   [_A("q"), _I("iterations"), _I("len_1d")],
    "s318":   [_CA("a"), _R("result"), _I("inc"), _I("iterations"), _I("len_1d")],
    "s319":   [_A("a"), _A("b"), _CA("c"), _CA("d"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s3110":  [_A("aa"), _A("bb"), _I("iterations"), _I("len_2d")],
    "s13110": [_A("aa"), _A("bb"), _I("iterations"), _I("len_2d")],
    "s3111":  [_CA("a"), _A("b"), _I("iterations"), _I("len_1d")],
    "s3112":  [_CA("a"), _A("b"), _I("iterations"), _I("len_1d")],
    "s3113":  [_CA("a"), _A("b"), _I("iterations"), _I("len_1d")],
    "s321":   [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "s322":   [_A("a"), _CA("b"), _CA("c"), _I("iterations"), _I("len_1d")],
    "s323":   [_A("a"), _A("b"), _CA("c"), _CA("d"), _CA("e"), _I("iterations"), _I("len_1d")],
    "s331":   [_CA("a"), _A("b"), _I("iterations"), _I("len_1d")],
    "s332":   [_CA("a"), _R("result"), _I("threshold"), _I("iterations"), _I("len_1d")],
    "s341":   [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "s342":   [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "s343":   [_CA("aa"), _CA("bb"), _A("flat_2d_array"), _I("iterations"), _I("len_2d")],
    "s351":   [_A("a"), _CA("b"), _CA("c"), _I("iterations"), _I("len_1d")],
    "s1351":  [_A("a"), _CA("b"), _CA("c"), _I("iterations"), _I("len_1d")],
    "s352":   [_CA("a"), _CA("b"), _A("c"), _I("iterations"), _I("len_1d")],
    "s353":   [_A("a"), _CA("b"), _CA("c"), _IA("ip"), _I("iterations"), _I("len_1d")],
    "s421":   [_CA("a"), _A("flat_2d_array"), _I("iterations"), _I("len_1d")],
    "s1421":  [_CA("a"), _A("b"), _I("iterations"), _I("len_1d")],
    "s422":   [_CA("a"), _A("flat_2d_array"), _I("iterations"), _I("len_1d")],
    "s423":   [_CA("a"), _A("flat_2d_array"), _I("iterations"), _I("len_1d")],
    "s424":   [_A("a"), _CA("flat"), _A("xx"), _I("iterations"), _I("len_1d")],
    "s431":   [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "s441":   [_A("a"), _CA("b"), _CA("c"), _CA("d"), _I("iterations"), _I("len_1d")],
    "s442":   [_A("a"), _CA("b"), _CA("c"), _CA("d"), _CA("e"), _IA("indx"), _I("iterations"), _I("len_1d")],
    "s443":   [_A("a"), _CA("b"), _CA("c"), _CA("d"), _I("iterations"), _I("len_1d")],
    "s451":   [_A("a"), _CA("b"), _CA("c"), _I("iterations"), _I("len_1d")],
    "s452":   [_A("a"), _CA("b"), _CA("c"), _I("iterations"), _I("len_1d")],
    "s453":   [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "s471":   [_A("b"), _CA("c"), _CA("d"), _CA("e"), _A("x"), _I("iterations"), _I("len_1d")],
    "s481":   [_A("a"), _CA("b"), _CA("c"), _CA("d"), _I("iterations"), _I("len_1d")],
    "s482":   [_A("a"), _CA("b"), _CA("c"), _I("iterations"), _I("len_1d")],
    "s491":   [_A("a"), _CA("b"), _CA("c"), _CA("d"), _IA("ip"), _I("iterations"), _I("len_1d")],
    "s4112":  [_A("a"), _CA("b"), _IA("ip"), _I("iterations"), _I("len_1d")],
    "s4113":  [_A("a"), _CA("b"), _CA("c"), _IA("ip"), _I("iterations"), _I("len_1d")],
    "s4114":  [_A("a"), _CA("b"), _CA("c"), _CA("d"), _IA("ip"), _I("iterations"), _I("len_1d"), _I("n1")],
    "s4115":  [_CA("a"), _CA("b"), _IA("ip"), _R("result_out"), _I("iterations"), _I("len_1d")],
    "s4116":  [_CA("a"), _CA("aa"), _IA("ip"), _R("sum_out"), _I("inc"), _I("iterations"), _I("j"), _I("len_1d"), _I("len_2d")],
    "s4117":  [_A("a"), _CA("b"), _CA("c"), _CA("d"), _I("iterations"), _I("len_1d")],
    "s4121":  [_A("a"), _CA("b"), _CA("c"), _I("iterations"), _I("len_1d")],
    "va":     [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "vag":    [_A("a"), _CA("b"), _IA("ip"), _I("iterations"), _I("len_1d")],
    "vas":    [_A("a"), _CA("b"), _IA("ip"), _I("iterations"), _I("len_1d")],
    "vif":    [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "vpv":    [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "vtv":    [_A("a"), _CA("b"), _I("iterations"), _I("len_1d")],
    "vpvtv":  [_A("a"), _CA("b"), _CA("c"), _I("iterations"), _I("len_1d")],
    "vpvts":  [_A("a"), _CA("b"), _I("iterations"), _I("len_1d"), _D("s")],
    "vpvpv":  [_A("a"), _CA("b"), _CA("c"), _I("iterations"), _I("len_1d")],
    "vtvtv":  [_A("a"), _CA("b"), _CA("c"), _I("iterations"), _I("len_1d")],
    "vsumr":  [_CA("a"), _R("sum_out"), _I("iterations"), _I("len_1d")],
    "vdotr":  [_CA("a"), _CA("b"), _R("dot_out"), _I("iterations"), _I("len_1d")],
    "vbor":   [_CA("a"), _CA("b"), _CA("c"), _CA("d"), _CA("e"), _A("x"), _I("iterations"), _I("len_2d")],
}
# fmt: on


def _to_carg(val, ctype_d, is_float):
    """Convert a Python/numpy value to the appropriate ctypes argument."""
    if isinstance(val, np.ndarray):
        if is_float and val.dtype == np.float64:
            val = val.astype(np.float32)
        elif not is_float and val.dtype == np.float32:
            val = val.astype(np.float64)
        if ctype_d == _ip or ctype_d == _ip:
            return val.ctypes.data_as(_ip)
        elif is_float:
            return val.ctypes.data_as(_fp)
        else:
            return val.ctypes.data_as(_dp)
    else:
        # Scalar
        if ctype_d == _int or ctype_d == _i32:
            return _int(int(val))
        elif ctype_d == _dbl:
            return _flt(float(val)) if is_float else _dbl(float(val))
        return val


class _KernelWrapper:
    """Callable wrapper for a single kernel variant."""

    __slots__ = ("_func", "_sig", "_is_float", "_name")

    def __init__(self, func, sig, is_float, name):
        self._func = func
        self._sig = sig
        self._is_float = is_float
        self._name = name

    def __call__(self, *args, **kwargs):
        # Build positional args from signature
        sig = self._sig
        if len(args) + len(kwargs) != len(sig):
            param_names = [s[0] for s in sig]
            raise TypeError(
                f"{self._name}() expects {len(sig)} args {param_names}, "
                f"got {len(args)} positional + {len(kwargs)} keyword"
            )

        # Merge positional and keyword
        cargs = []
        for i, (pname, ctype_d, ctype_f) in enumerate(sig):
            if i < len(args):
                val = args[i]
            elif pname in kwargs:
                val = kwargs[pname]
            else:
                raise TypeError(f"{self._name}(): missing argument '{pname}'")
            cargs.append(_to_carg(val, ctype_d, self._is_float))

        # Append time_ns output
        time_ns = np.zeros(1, dtype=np.int64)
        cargs.append(time_ns.ctypes.data_as(_i64p))

        self._func(*cargs)
        return time_ns[0]

    def __repr__(self):
        params = ", ".join(s[0] for s in self._sig)
        return f"<kernel {self._name}({params}) -> ns>"


class TSVCLibrary:
    """
    Load libtsvc_kernels.so and expose every kernel as a typed callable.

    If the .so does not exist, the split + compile pipeline runs automatically:
      1. split_cpp_kernels.py splits tsvc2_core.cpp into per-kernel sources
      2. compile_cpp_kernels.py compiles all .o and links into one .so

    Parameters
    ----------
    so_path     : Path to the shared library (default: .tsvc_build/libtsvc_kernels.so)
    kernel_root : Directory containing per-kernel .cpp files (default: tsvc_cpp_microkernels)
    core_cpp    : Path to monolithic C++ source for splitting (default: tsvc2_core.cpp)
    build_dir   : Build directory for .o and .so files (default: .tsvc_build)
    jobs        : Parallel compile jobs for auto-build (default: nproc)
    """

    def __init__(
        self,
        so_path: str | pathlib.Path = ".tsvc_build/libtsvc_kernels.so",
        kernel_root: str | pathlib.Path = "tsvc_cpp_microkernels",
        core_cpp: str | pathlib.Path = "tsvc2_core.cpp",
        build_dir: str | pathlib.Path = ".tsvc_build",
        jobs: Optional[int] = None,
    ):
        so_path = pathlib.Path(so_path)

        if not so_path.exists():
            self._auto_build(so_path, kernel_root, core_cpp, build_dir, jobs)

        self._lib = ctypes.CDLL(str(so_path))
        self._kernels: dict[str, _KernelWrapper] = {}

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
                argtypes.append(_i64p)  # time_ns
                func.argtypes = argtypes
                func.restype = None

                wrapper = _KernelWrapper(func, sig, is_float, name)
                self._kernels[name] = wrapper

    @staticmethod
    def _auto_build(so_path, kernel_root, core_cpp, build_dir, jobs):
        """Split and compile kernels if the .so is missing."""
        kernel_root = pathlib.Path(kernel_root)
        core_cpp = pathlib.Path(core_cpp)
        build_dir = pathlib.Path(build_dir)
        if jobs is None:
            jobs = os.cpu_count() or 1

        # Step 1: split if kernel directory is empty or missing
        if not kernel_root.exists() or not any(kernel_root.rglob("*.cpp")):
            if not core_cpp.exists():
                raise FileNotFoundError(
                    f"Cannot auto-build: {core_cpp} not found. "
                    f"Either provide the monolithic source or pre-split kernels in {kernel_root}/."
                )
            print(f"Splitting {core_cpp} → {kernel_root}/ ...")
            from split_cpp_kernels import main as split_main
            import sys
            old_argv = sys.argv
            sys.argv = ["split_cpp_kernels", "-i", str(core_cpp), "-o", str(kernel_root)]
            try:
                split_main()
            finally:
                sys.argv = old_argv

        # Step 2: compile
        print(f"Compiling {kernel_root}/ → {so_path} (-j{jobs}) ...")
        from compile_cpp_kernels import compile_library
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

    def list_kernels(self) -> list[str]:
        """Return sorted list of available kernel names."""
        return sorted(self._kernels.keys())

    def __repr__(self):
        return f"<TSVCLibrary: {len(self._kernels)} kernels>"