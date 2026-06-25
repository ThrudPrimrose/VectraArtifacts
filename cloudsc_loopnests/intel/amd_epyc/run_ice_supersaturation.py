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

from dace.transformation.interstate.loop_to_map import LoopToMap
from dace.transformation.passes import ConstantPropagation, EliminateBranches, OffsetLoopsAndMaps
from dace.transformation.passes.prune_symbols import RemoveUnusedSymbols
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
    '-Wno-unused-parameter', '-Wno-unused-label',
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

def generate_ice_supersaturation_data() -> Dict[str, np.ndarray]:
    """
    Generate synthetic but consistent data for ice_supersaturation_adjustment.
    Following the same style and dimensions as rain evaporation.
    """

    # Choose species indices consistent with scalar_specialization_values
    ncldql_val = np.int32(1)  # liquid cloud water
    ncldqi_val = np.int32(2)  # ice cloud water
    ncldqv_val = np.int32(5)  # vapour

    # Scalars
    rtt      = np.float64(273.16)
    ramin    = np.float64(1e-3)      # min clear fraction
    rthomo   = np.float64(233.16)    # homogenous freezing threshold
    nssopt   = np.int32(1)           # activate Koop scheme
    rkooptau = np.float64(60.0)     # characteristic timescale [s]
    ptsphy   = np.float64(2.0)       # timestep [s]
    zepsec   = np.float64(1e-12)

    # Temperature (some below RTT, some above)
    ztp1 = np.linspace(230.0, 280.0, klon_val).astype(np.float64)

    # Cloud fraction
    za = (0.05 + 0.9 * np.random.rand(klon_val)).astype(np.float64)

    # Vapour content
    zqx_ncldqv = (0.02 * np.random.rand(klon_val)).astype(np.float64)

    # Ice saturation mixing ratio
    zqsice = (1e-4 + 2e-3 * np.random.rand(klon_val)).astype(np.float64)

    # Correction factor for ice saturation
    zcorqsice = (0.5 + 0.5 * np.random.rand(klon_val)).astype(np.float64)

    # Koop factor between 0 and 1
    zfokoop = np.random.rand(klon_val).astype(np.float64)

    # 3D source-sink tensor: initialize to zeros
    zsolqa = np.zeros((nclv_val, nclv_val, klon_val), dtype=np.float64)

    # Accretion / supersat activation term
    zsolac = np.zeros(klon_val, dtype=np.float64)

    # QXFG(KLON, NCLV): current species mixing ratios, start with small noise
    zqxfg = (1e-5 * np.random.rand(nclv_val, klon_val)).astype(np.float64)
    timer = np.zeros((2,), dtype=np.float64)

    return dict(
        ztp1=ztp1,
        za=za,
        zqx_ncldqv=zqx_ncldqv,
        zqsice=zqsice,
        zcorqsice=zcorqsice,
        zfokoop=zfokoop,
        zsolqa=zsolqa,
        zsolac=zsolac,
        zqxfg=zqxfg,
        rtt=rtt,
        ramin=ramin,
        rthomo=rthomo,
        nssopt=nssopt,
        rkooptau=rkooptau,
        ptsphy=ptsphy,
        zepsec=zepsec,
        ncldql=np.int32(ncldql_val),
        ncldqi=np.int32(ncldqi_val),
        ncldqv=np.int32(ncldqv_val),
        kidia=np.int32(1),
        kfdia=np.int32(klon_val),
        klon=np.int32(klon_val),
        klev=np.int32(klev_val),
        nclv=np.int32(nclv_val),
        timer=timer,
        sym_klon=klon_val,
        sym_klev=klev_val
    )

def compile_ice_supersaturation_fortran(
    src_path: str = "./ice_supersaturation_adjustment.f90",
    libname: str = "libice_supersaturation.so",
    func_name: str = "ice_supersaturation_adjustment",
):
    """
    Compile the ice_supersaturation_adjustment Fortran routine into a shared library
    and return a ctypes function handle.
    """
    if not os.path.exists(src_path):
        raise FileNotFoundError(f"Fortran source not found: {src_path}")

    cxx = os.environ["CXX"]
    if cxx.endswith("clang++"):
        f90 = "flang"
        #c1 = "-fno-math-errno"
        #c2 = "-fveclib=libmvec"
    elif cxx.endswith("g++"):
        f90 = "gfortran"
    else:
        assert cxx.endswith("icpx")
        f90 = "ifx"

    cmd = [f90, "-O3",  "-fPIC", "-shared", "-ffast-math",  src_path, "-o", libname]
    print("Compiling Fortran:", " ".join(cmd))
    subprocess.check_call(cmd)
    print(f"Built {libname}")

    lib = ctypes.CDLL(f"./{libname}")
    try:
        func = getattr(lib, func_name)
    except AttributeError:
        raise RuntimeError(f"Fortran symbol '{func_name}' not found in shared library.")

    ndF64_1d = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags="F_CONTIGUOUS")
    ndF64_2d = np.ctypeslib.ndpointer(dtype=np.float64, ndim=2, flags="F_CONTIGUOUS")
    ndF64_3d = np.ctypeslib.ndpointer(dtype=np.float64, ndim=3, flags="F_CONTIGUOUS")

    func.restype = None
    func.argtypes = [
        ctypes.c_int,   # KIDIA
        ctypes.c_int,   # KFDIA
        ctypes.c_int,   # KLON
        ndF64_1d,       # ZTP1
        ndF64_1d,       # ZA
        ndF64_1d,       # ZQX_NCLDQV
        ndF64_1d,       # ZQSICE
        ndF64_1d,       # ZCORQSICE
        ndF64_1d,       # ZFOKOOP
        ndF64_3d,       # ZSOLQA
        ndF64_1d,       # ZSOLAC
        ndF64_2d,       # ZQXFG
        ctypes.c_double,  # RTT
        ctypes.c_double,  # RAMIN
        ctypes.c_double,  # RTHOMO
        ctypes.c_int,     # NSSOPT
        ctypes.c_double,  # RKOOPTAU
        ctypes.c_double,  # PTSPHY
        ctypes.c_double,  # ZEPSEC
        ctypes.c_int,     # NCLDQL
        ctypes.c_int,     # NCLDQI
        ctypes.c_int,     # NCLDQV
        ctypes.c_int,     # NCLV
        ndF64_1d, # timer
    ]

    print("Fortran function loaded (ice supersaturation)")
    return func

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


def wrap_ice_supersaturation(func):
    """
    Thin wrapper to call the Fortran ice_supersaturation_adjustment routine
    using a kwargs dict consistent with the Python/Dace naming.
    """
    arg_order = [
        "kidia", "kfdia", "klon",
        "ztp1", "za", "zqx_ncldqv", "zqsice", "zcorqsice", "zfokoop",
        "zsolqa", "zsolac", "zqxfg",
        "rtt", "ramin", "rthomo", "nssopt", "rkooptau", "ptsphy", "zepsec",
        "ncldql", "ncldqi", "ncldqv", "nclv", "timer"
    ]

    def wrapper(**kwargs):
        args = [kwargs[name] for name in arg_order]
        return func(*args)

    return wrapper

def run_ice_supersaturation():
    # ===== Generate Inputs =====
    base_data   = generate_ice_supersaturation_data()
    data_F      = make_col_major(copy.deepcopy(base_data))
    data_F_dace = make_col_major(copy.deepcopy(base_data))

    # ===== Build SDFG =====
    sdfg = dace.SDFG.from_file("ice_supersaturation_adjustment.sdfg")
    sdfg.name = "ice_supersaturation_adjustment"

    from dace.transformation.passes.vectorization.tasklet_preprocessing_passes import (
        PowerOperatorExpansion,
        RemoveFPTypeCasts,
        RemoveIntTypeCasts,
    )

    # Preprocessing
    PowerOperatorExpansion().apply_pass(sdfg, {})
    RemoveFPTypeCasts().apply_pass(sdfg, {})
    RemoveIntTypeCasts().apply_pass(sdfg, {})
    OffsetLoopsAndMaps(offset_expr="-1", begin_expr=None).apply_pass(sdfg, {})
    sdfg.apply_transformations_repeated(LoopToMap)
    sdfg.simplify()
    sdfg.save("ice_supersaturation_par.sdfg")

    # ===== Scalar specialization =====
    for scalar_name, scalar_value in scalar_specialization_values.items():
        if scalar_name in sdfg.arrays:
            sdutil.specialize_scalar(
                sdfg=sdfg, scalar_name=scalar_name, scalar_val=scalar_value
            )
            sdfg.validate()
        if scalar_name in sdfg.symbols:
            sdfg.replace_dict({scalar_name: scalar_value})
            sdfg.remove_symbol(scalar_name)

    repldict = {
        "sym_nclv": 5,
        "sym_ncldqs": scalar_specialization_values["ncldqs"],
        "sym_ncldqi": scalar_specialization_values["ncldqi"],
        "sym_ncldqv": scalar_specialization_values["ncldqv"],
    }
    sdfg.replace_dict(repldict)
    for sym in repldict:
        if sym in sdfg.symbols:
            sdfg.remove_symbol(sym)

    sdfg.validate()
    RemoveUnusedSymbols().apply_pass(sdfg, {})

    # ===== Instrumentation and scheduling =====
    sdfg.instrument = dace.dtypes.InstrumentationType.Timer
    sdfg.simplify()
    set_map_sched(sdfg)

    # ===== Baseline DaCe =====
    compiled = sdfg.compile()
    compiled(**data_F_dace)

    report = sdfg.get_latest_report()
    dace_total_time = report.events[0].duration
    print(f"Run time SDFG ({sdfg.name}): {dace_total_time} us")
    write_runtime(f"ice_supersaturation{env_suffix_str}_v3", "dace", dace_total_time)

    # ===== Baseline Fortran =====
    raw_func = compile_ice_supersaturation_fortran(
        "./ice_supersaturation_adjustment_w_timer.f90",
        "libice_supersaturation.so",
        "ice_supersaturation_adjustment",
    )
    fortran_func = wrap_ice_supersaturation(raw_func)

    fortran_func(**data_F)
    fortran_total_time = float(data_F["timer"][0])
    print(f"Run time Fortran: {fortran_total_time} us")
    write_runtime(f"ice_supersaturation{env_suffix_str}_v3", "fortran", fortran_total_time)

    # ===== Compare baseline =====
    print("Ice supersaturation (DaCe vs Fortran) comparison:")
    if compare_row_col_dicts(data_F_dace, data_F, rtol=1e-12, atol=1e-12):

        # Repeated DaCe timings (mutated data_F_dace)
        for rep in range(10):
            compiled(**data_F_dace)
            report = sdfg.get_latest_report()
            dace_rep = report.events[0].duration
            print(f"  Run DaCe {rep+1}/10: {dace_rep} us")
            write_runtime(
                f"ice_supersaturation{env_suffix_str}_v3",
                "dace",
                dace_rep,
            )

    del data_F_dace

    # Repeated Fortran timings (fresh deep copy)
    repeat_F = make_col_major(copy.deepcopy(base_data))
    for rep in range(10):
        fortran_func(**repeat_F)
        ftime = float(repeat_F["timer"][0])
        print(f"  Run Fortran {rep+1}/10: {ftime} us")
        write_runtime(
            f"ice_supersaturation{env_suffix_str}_v3",
            "fortran",
            ftime,
        )

    # ===== Vectorization sweep =====
    if cpu_name == "intel_xeon":
        vlens = [8, 16, 32, 64]
    elif cpu_name == "amd_epyc":
        vlens = [4, 8, 16, 32, 64]
    else:
        vlens = [2, 4, 8, 16, 32, 64]

    for vlen in vlens:
        for cpy in [True, False]:

            # First vec run: fresh inputs
            data_F_dace_vec = make_col_major(copy.deepcopy(base_data))

            vec_sdfg = copy.deepcopy(sdfg)
            vec_sdfg.name = f"{sdfg.name}_vec_v{vlen}_cpy{int(cpy)}"
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
            vec_sdfg.save(f"ice_supersaturation_{vlen}.sdfg")

            vec_compiled = vec_sdfg.compile()
            vec_compiled(**data_F_dace_vec)

            report = vec_sdfg.get_latest_report()
            dace_vec_time = report.events[0].duration

            print("Ice supersaturation (DaCe-Vec vs Fortran) comparison:")
            if compare_row_col_dicts(
                data_F_dace_vec, data_F, rtol=1e-12, atol=1e-12
            ):
                print(f"Run time SDFG ({vec_sdfg.name}): {dace_vec_time} us")
                write_runtime(
                    f"ice_supersaturation{env_suffix_str}_v3",
                    "dace_vec",
                    dace_vec_time,
                    vlen=vlen,
                    cpy=cpy,
                )

                # 10× repeated vector run (mutated data_F_dace_vec)
                for rep in range(10):
                    vec_compiled(**data_F_dace_vec)
                    report = vec_sdfg.get_latest_report()
                    vec_rep = report.events[0].duration
                    print(f"  Run {rep+1}/10: {vec_rep} us")
                    write_runtime(
                        f"ice_supersaturation{env_suffix_str}_v3",
                        "dace_vec",
                        vec_rep,
                        vlen=vlen,
                        cpy=cpy,
                    )

if __name__ == "__main__":
    run_ice_supersaturation()