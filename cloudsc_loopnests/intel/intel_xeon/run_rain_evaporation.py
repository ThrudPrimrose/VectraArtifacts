"""
Saturation Values Calculation - DaCe Version
"""

import copy
from typing import Any, Dict
import dace
import math
import numpy as np
import dace.sdfg.utils as sdutil
import subprocess
import ctypes
import os
from typing import Callable
from math import exp, log, pow, sqrt

from dace.transformation.dataflow.wcr_conversion import WCRToAugAssign
from dace.transformation.interstate.loop_to_map import LoopToMap
from dace.transformation.passes.constant_propagation import ConstantPropagation
from dace.transformation.passes.eliminate_branches import EliminateBranches
from dace.transformation.passes.offset_loop_and_maps import OffsetLoopsAndMaps
from dace.transformation.passes.prune_symbols import RemoveUnusedSymbols
from dace.transformation.passes.split_tasklets import SplitTasklets
from dace.transformation.passes.vectorization.vectorize_cpu import VectorizeCPU
from dace.utils.log_runtime import compare_row_col_dicts, write_runtime

# Define symbolic sizes
klev = dace.symbol("klev")
klon = dace.symbol("klon")
nclv = dace.symbol("nclv")
def _read_env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be an integer, got: {val}")

# Default values same as your other runners
# Default values same as your other runners
klev_val = int(_read_env_int("__DACE_KLEV", 8))
klon_val = int(_read_env_int("__DACE_KLON", 8192*512))
nclv_val = 5


cpu_name = os.environ.get('CPU_NAME', 'amd_epyc')
compiler_exec = os.environ.get('CXX', 'c++')
dace.config.Config.set("compiler", "cpu", "executable", value=compiler_exec)

# Base compilation flags
base_flags = [
    '-fopenmp', '-fstrict-aliasing', '-std=c++17', '-faligned-new',
    '-fPIC', '-Wall', '-Wextra', '-O3', '-march=native', '-ffast-math',
    '-Wno-unused-parameter', '-Wno-unused-label'
]


if cpu_name == "arm":
    base_flags.remove("-march=native")

if compiler_exec == "icpx":
    base_flags.remove("-fopenmp")
    base_flags.append("-qopenmp")
if compiler_exec.endswith("clang++"):
    base_flags.append("-fno-math-errno")
    #base_flags.append("-fveclib=libmvec")

# Architecture / compiler specific extra flags
env_flags_str = os.environ.get('EXTRA_FLAGS', '')
base_flags_str = ' '.join(base_flags)

flags = base_flags_str + " " + env_flags_str if env_flags_str != '' else base_flags_str
dace.config.Config.set("compiler", "cpu", "args", value=flags)


multi_core = int(os.environ.get('RUN_MULTICORE', '0')) == 1
core_count = 1


multicore_suffix = '' if core_count == 1 else '_multicore'

if multi_core:
    if cpu_name == "arm":
        core_count = 72
    elif cpu_name == "intel_xeon":
        core_count = 18
    elif cpu_name == "amd_epyc":
        core_count = 64

env_suffix_str = os.environ.get('SUFFIX', '')
if env_suffix_str != '':
    env_suffix_str = "_" + env_suffix_str
env_suffix_str += f"_size_{klon_val}"


scalar_specialization_values = {
    "nclv": 5,      # number of microphysics variables
    "sym_nclv": 5,  # number of microphysics variables
    "ncldql": 1,    # liquid cloud water
    "ncldqi": 2,    # ice cloud water
    "ncldqr": 3,    # rain water
    "ncldqs": 4,    # snow
    "ncldqv": 5,    # vapour
    'nssopt': 1,
    'laericesed': 0
}

def make_col_major(arrays: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """
    Deep-copy the dictionary and convert all multi-dimensional NumPy arrays
    (ndim >= 2) to Fortran-contiguous arrays.
    
    Scalars, None, and other objects are deep-copied normally.
    """
    out = {}

    for key, val in arrays.items():

        if isinstance(val, np.ndarray) and val.ndim >= 2:
            # Deep copy + force Fortran layout
            out[key] = np.asfortranarray(val.copy())
        elif isinstance(val, np.ndarray):
            # 1D arrays → regular deep copy (no F-order needed)
            out[key] = val.copy()
        else:
            # Non-array (scalars, ints, floats, custom objects) → deep-copy
            out[key] = copy.deepcopy(val)

    return out

def set_map_sched(sdfg: dace.SDFG):
    for n, g in sdfg.all_nodes_recursive():
        if isinstance(n, dace.nodes.MapEntry):
            n.map.schedule = dace.dtypes.ScheduleType.Sequential
        if isinstance(n, dace.nodes.NestedSDFG):
            for arr_name, arr in n.sdfg.arrays.items():
                if arr.storage == dace.dtypes.StorageType.Default and arr.transient is True:
                    arr.storage = dace.dtypes.StorageType.Register
    for arr_name, arr in sdfg.arrays.items():
        if arr.storage == dace.dtypes.StorageType.Default and arr.transient is True:
            arr.storage = dace.dtypes.StorageType.Register


def generate_rain_evaporation_data() -> Dict[str, np.ndarray]:
    """
    Generate synthetic but reasonable data for rain_evaporation_abel_boutle.
    """

    # Indices for vapour and rain in the NCLV dimension
    ncldqv_val = np.int32(5)  # e.g., vapour index
    ncldqr_val = np.int32(3)  # e.g., rain index

    # Scalars
    rtt        = np.float64(273.16)
    rv         = np.float64(461.5)   # J/kg/K
    rd         = np.float64(287.05)  # J/kg/K
    rprecrhmax = np.float64(0.7)
    rcovpmin   = np.float64(1e-3)
    rdensref   = np.float64(1.225)
    ptsphy     = np.float64(2.0)    # time step [s]
    zepsec     = np.float64(1e-12)

    rcl_fac1   = np.float64(1.0)
    rcl_fac2   = np.float64(0.5)
    rcl_cdenom1 = np.float64(1.0)
    rcl_cdenom2 = np.float64(1e-3)
    rcl_cdenom3 = np.float64(1e-9)
    rcl_ka273   = np.float64(0.024)

    rcl_const1r = np.float64(0.2)
    rcl_const2r = np.float64(0.2)
    rcl_const3r = np.float64(0.2)
    rcl_const4r = np.float64(0.2)

    # Temperature [K], 260–290
    ztp1 = np.linspace(260.0, 290.0, klon_val).astype(np.float64)

    # Vapour mixing ratio (0–0.02)
    zqx_ncldqv = (0.02 * np.random.rand(klon_val)).astype(np.float64)

    # Cloud fraction (0.1–0.9)
    za = (0.01 + 0.8 * np.random.rand(klon_val)).astype(np.float64)

    # Saturation specific humidity, strictly positive
    zqsliq = (1e-4 + 2e-3 * np.random.rand(klon_val)).astype(np.float64)

    # Rain water content (some positive values)
    zqxfg_ncldqr = (1e-4 + 1e-3 * np.random.rand(klon_val)).astype(np.float64)

    # Column-covering precipitating area etc.
    zcovptot = (0.05 + 0.7 * np.random.rand(klon_val)).astype(np.float64)
    zcovpclr = (0.05 + 0.6 * np.random.rand(klon_val)).astype(np.float64)
    zcovpmax = np.maximum(zcovptot, zcovpclr)

    # Density [kg/m^3]
    zrho = (0.3 + 0.8 * np.random.rand(klon_val)).astype(np.float64)

    # Pressure [Pa]
    pap = (7e4 + 4e4 * np.random.rand(klon_val)).astype(np.float64)

    # 3D source-sink tensor: init to zero
    zsolqa = np.random.rand(nclv_val, nclv_val, klon_val).astype(np.float64)

    # Output evaporation rate
    zevap_out = np.random.rand(klon_val).astype(np.float64)
    timer = np.zeros((2,), np.float64)

    return dict(
        ztp1=ztp1,
        zqx_ncldqv=zqx_ncldqv,
        za=za,
        zqsliq=zqsliq,
        zqxfg_ncldqr=zqxfg_ncldqr,
        zcovptot=zcovptot,
        zcovpclr=zcovpclr,
        zcovpmax=zcovpmax,
        zrho=zrho,
        pap=pap,
        zsolqa=zsolqa,
        zevap_out=zevap_out,
        rtt=rtt,
        rv=rv,
        rd=rd,
        rprecrhmax=rprecrhmax,
        rcovpmin=rcovpmin,
        rdensref=rdensref,
        ptsphy=ptsphy,
        zepsec=zepsec,
        rcl_fac1=rcl_fac1,
        rcl_fac2=rcl_fac2,
        rcl_cdenom1=rcl_cdenom1,
        rcl_cdenom2=rcl_cdenom2,
        rcl_cdenom3=rcl_cdenom3,
        rcl_ka273=rcl_ka273,
        rcl_const1r=rcl_const1r,
        rcl_const2r=rcl_const2r,
        rcl_const3r=rcl_const3r,
        rcl_const4r=rcl_const4r,
        ncldqv=np.int32(ncldqv_val),
        ncldqr=np.int32(ncldqr_val),
        nclv=np.int32(nclv_val),
        kidia=np.int32(1),
        kfdia=np.int32(klon_val),
        klon=np.int32(klon_val),
        klev=np.int32(klev_val),
        timer=timer,
        sym_klon=klon_val,
        sym_klev=klev_val
    )


def compile_rain_evaporation_fortran(
    src_path: str = "./rain_evaporation_abel_boutle.f90",
    libname: str = "librain_evaporation.so",
    func_name: str = "rain_evaporation_abel_boutle",
):
    """
    Compile the rain_evaporation_abel_boutle Fortran routine into a shared library
    and return a ctypes function handle.
    """
    if not os.path.exists(src_path):
        raise FileNotFoundError(f"Fortran source not found: {src_path}")

    cxx = os.environ["CXX"]
    if cxx.endswith("clang++"):
        f90 = "flang"
    elif cxx.endswith("g++"):
        f90 = "gfortran"
    else:
        assert cxx.endswith("icpx")
        f90 = "ifx"

    cmd = [f90, "-O3",  "-fPIC", "-shared", "-ffast-math", src_path, "-o", libname]
    print("Compiling Fortran:", " ".join(cmd))
    subprocess.check_call(cmd)
    print(f"Built {libname}")

    lib = ctypes.CDLL(f"./{libname}")
    try:
        func = getattr(lib, func_name)
    except AttributeError:
        raise RuntimeError(f"Fortran symbol '{func_name}' not found in shared library.")

    # Argtypes: match Fortran signature, all arrays are F-contiguous
    ndF64_1d = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags="F_CONTIGUOUS")
    ndF64_3d = np.ctypeslib.ndpointer(dtype=np.float64, ndim=3, flags="F_CONTIGUOUS")

    func.restype = None
    func.argtypes = [
        ctypes.c_int,  # KIDIA
        ctypes.c_int,  # KFDIA
        ctypes.c_int,  # KLON
        ndF64_1d,      # ZTP1
        ndF64_1d,      # ZQX_NCLDQV
        ndF64_1d,      # ZA
        ndF64_1d,      # ZQSLIQ
        ndF64_1d,      # ZQXFG_NCLDQR
        ndF64_1d,      # ZCOVPTOT
        ndF64_1d,      # ZCOVPCLR
        ndF64_1d,      # ZCOVPMAX
        ndF64_1d,      # ZRHO
        ndF64_1d,      # PAP
        ndF64_3d,      # ZSOLQA
        ndF64_1d,      # ZEVAP_OUT
        ctypes.c_double,  # RTT
        ctypes.c_double,  # RV
        ctypes.c_double,  # RD
        ctypes.c_double,  # RPRECRHMAX
        ctypes.c_double,  # RCOVPMIN
        ctypes.c_double,  # RDENSREF
        ctypes.c_double,  # PTSPHY
        ctypes.c_double,  # ZEPSEC
        ctypes.c_double,  # RCL_FAC1
        ctypes.c_double,  # RCL_FAC2
        ctypes.c_double,  # RCL_CDENOM1
        ctypes.c_double,  # RCL_CDENOM2
        ctypes.c_double,  # RCL_CDENOM3
        ctypes.c_double,  # RCL_KA273
        ctypes.c_double,  # RCL_CONST1R
        ctypes.c_double,  # RCL_CONST2R
        ctypes.c_double,  # RCL_CONST3R
        ctypes.c_double,  # RCL_CONST4R
        ctypes.c_int,     # NCLDQV
        ctypes.c_int,     # NCLDQR
        ctypes.c_int,     # 
        ndF64_1d, #timer
    ]

    print("Fortran function loaded")
    return func


def wrap_rain_evaporation(func):
    """
    Thin wrapper to call the Fortran routine using a kwargs dict
    consistent with the Python/Dace naming.
    """
    arg_order = [
        "kidia", "kfdia", "klon",
        "ztp1", "zqx_ncldqv", "za", "zqsliq", "zqxfg_ncldqr",
        "zcovptot", "zcovpclr", "zcovpmax", "zrho", "pap",
        "zsolqa", "zevap_out",
        "rtt", "rv", "rd", "rprecrhmax", "rcovpmin", "rdensref",
        "ptsphy", "zepsec",
        "rcl_fac1", "rcl_fac2",
        "rcl_cdenom1", "rcl_cdenom2", "rcl_cdenom3",
        "rcl_ka273",
        "rcl_const1r", "rcl_const2r", "rcl_const3r", "rcl_const4r",
        "ncldqv", "ncldqr", "nclv", "timer"
    ]

    def wrapper(**kwargs):
        args = [kwargs[name] for name in arg_order]
        return func(*args)

    return wrapper

def run_rain_evaporation():
    # ----- Generate Inputs -----
    base_data        = generate_rain_evaporation_data()
    data_F           = make_col_major(copy.deepcopy(base_data))   # Fortran baseline
    data_F_dace      = make_col_major(copy.deepcopy(base_data))   # DaCe baseline

    # ----- Build SDFG -----
    sdfg = dace.SDFG.from_file("rain_evaporation.sdfg")
    sdfg.validate()
    sdfg.name = "rain_evaporation_abel_boutle"

    from dace.transformation.passes.vectorization.tasklet_preprocessing_passes import (
        PowerOperatorExpansion, RemoveFPTypeCasts, RemoveIntTypeCasts,
    )

    RemoveFPTypeCasts().apply_pass(sdfg, {})
    RemoveIntTypeCasts().apply_pass(sdfg, {})
    sdfg.simplify()

    # ----- Specialize scalars -----
    for scalar_name, scalar_value in scalar_specialization_values.items():
        if scalar_name in sdfg.arrays:
            sdutil.specialize_scalar(
                sdfg=sdfg, scalar_name=scalar_name, scalar_val=scalar_value
            )
            sdfg.validate()
        if scalar_name in sdfg.symbols:
            sdfg.replace_dict({scalar_name: scalar_value})
            sdfg.remove_symbol(scalar_name)

    sdfg.validate()

    # Replace symbolic constants
    sdfg.replace_dict({"sym_nclv": 5})
    if "sym_nclv" in sdfg.symbols:
        sdfg.remove_symbol("sym_nclv")
    sdfg.validate()

    # Further passes
    PowerOperatorExpansion().apply_pass(sdfg, {})
    RemoveFPTypeCasts().apply_pass(sdfg, {})
    RemoveIntTypeCasts().apply_pass(sdfg, {})
    sdfg.apply_transformations_repeated(WCRToAugAssign)
    OffsetLoopsAndMaps(offset_expr="-1", begin_expr=None).apply_pass(sdfg, {})
    sdfg.apply_transformations_repeated(LoopToMap)

    sdfg.instrument = dace.dtypes.InstrumentationType.Timer
    set_map_sched(sdfg)

    # ---------------------------------------------------------------------
    #  BASELINE: DaCe (1×)
    # ---------------------------------------------------------------------
    compiled = sdfg.compile()
    compiled(**data_F_dace)

    report = sdfg.get_latest_report()
    dace_total_time = report.events[0].duration
    print(f"Run time SDFG ({sdfg.name}): {float(dace_total_time)} us")
    write_runtime(f"rain_evaporation{env_suffix_str}_v3", "dace", dace_total_time)

    # ---------------------------------------------------------------------
    #  BASELINE: Fortran (1×)
    # ---------------------------------------------------------------------
    raw_func = compile_rain_evaporation_fortran(
        "./rain_evaporation_abel_boutle_w_timer.f90",
        "librain_evaporation.so",
        "rain_evaporation_abel_boutle",
    )
    fortran_func = wrap_rain_evaporation(raw_func)
    fortran_func(**data_F)
    fortran_total_time = float(data_F["timer"][0])
    print(f"Run time Fortran: {fortran_total_time} us")
    write_runtime(f"rain_evaporation{env_suffix_str}_v3", "fortran", fortran_total_time)

    # ---------------------------------------------------------------------
    #  BASELINE COMPARISON + REPEATED (10×) TIMING
    # ---------------------------------------------------------------------
    print("Rain evaporation (DaCe vs Fortran) comparison:")

    if compare_row_col_dicts(data_F_dace, data_F, rtol=1e-12, atol=1e-12):

        # ---- 10× repeated DACE baseline ----
        for rep in range(10):
            compiled(**data_F_dace)
            report = sdfg.get_latest_report()
            dace_time = report.events[0].duration
            print(f"  Run DaCe {rep+1}/10: {dace_time} us")
            write_runtime(f"rain_evaporation{env_suffix_str}_v3", "dace", dace_time)

    del data_F_dace

    # ---- 10× repeated FORTRAN baseline ----
    fortran_repeat_data = make_col_major(copy.deepcopy(base_data))
    for rep in range(10):
        fortran_func(**fortran_repeat_data)
        ft_time = float(fortran_repeat_data["timer"][0])
        print(f"  Run Fortran {rep+1}/10: {ft_time} us")
        write_runtime(f"rain_evaporation{env_suffix_str}_v3", "fortran", ft_time)

    # ---------------------------------------------------------------------
    #  VECTORIZATION SWEEP (identical structure to autoconversion_snow)
    # ---------------------------------------------------------------------
    if cpu_name == "intel_xeon":
        vlens = [8, 16, 32, 64]
    elif cpu_name == "amd_epyc":
        vlens = [4, 8, 16, 32, 64]
    else:
        vlens = [2, 4, 8, 16, 32, 64]

    for vlen in vlens:
        for cpy in [False, True]:

            # Fresh data for comparison
            data_F_dace_vec = make_col_major(copy.deepcopy(base_data))

            vec_sdfg = copy.deepcopy(sdfg)
            vec_sdfg.name = f"{sdfg.name}_vectorized_v{vlen}_cpy{int(cpy)}"
            vec_sdfg.instrument = dace.dtypes.InstrumentationType.Timer

            eb = EliminateBranches()
            eb.try_clean = True
            eb.apply_pass(vec_sdfg, {})
            ConstantPropagation().apply_pass(vec_sdfg, {})
            RemoveUnusedSymbols().apply_pass(vec_sdfg, {})

            VectorizeCPU(
                vector_width=vlen,
                try_to_demote_symbols_in_nsdfgs=True,
                fuse_overlapping_loads=False,
                insert_copies=cpy,
                eliminate_trivial_vector_map=True,
            ).apply_pass(vec_sdfg, {})

            set_map_sched(vec_sdfg)

            vec_compiled = vec_sdfg.compile()
            vec_compiled(**data_F_dace_vec)

            report = vec_sdfg.get_latest_report()
            dace_vec_time = report.events[0].duration

            print("Rain evaporation (DaCe-Vec vs Fortran) comparison:")
            if compare_row_col_dicts(
                data_F_dace_vec, data_F, rtol=1e-12, atol=1e-12
            ):
                print(
                    f"Run time SDFG ({vec_sdfg.name}): {float(dace_vec_time)} us"
                )

                write_runtime(
                    f"rain_evaporation{env_suffix_str}_v3",
                    "dace_vec",
                    dace_vec_time,
                    vlen=vlen,
                    cpy=cpy,
                )

                # ---- 10× repeated vectorized runs ----
                for rep in range(10):
                    vec_compiled(**data_F_dace_vec)
                    r = vec_sdfg.get_latest_report().events[0].duration
                    print(f"  Run {rep+1}/10: {r} us")
                    write_runtime(
                        f"rain_evaporation{env_suffix_str}_v3",
                        "dace_vec",
                        r,
                        vlen=vlen,
                        cpy=cpy,
                    )

if __name__ == "__main__":
    run_rain_evaporation()
