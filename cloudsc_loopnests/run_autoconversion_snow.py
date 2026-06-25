"""
Autoconversion Snow - DaCe vs Fortran Runner
"""

import copy
import csv
from pathlib import Path
from typing import Dict
import dace
import numpy as np
import dace.sdfg.utils as sdutil
import subprocess
import ctypes
import os
from dace.transformation.interstate.loop_to_map import LoopToMap
from dace.transformation.passes import ConstantPropagation, EliminateBranches, OffsetLoopsAndMaps
from dace.transformation.passes.prune_symbols import RemoveUnusedSymbols
from dace.transformation.passes.vectorization.vectorize_cpu import VectorizeCPU
from dace.transformation.passes.scalar_fission import ScalarFission
from dace.transformation.passes import RemoveUnusedSymbols, analysis as ap
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

cpu_name = os.environ.get('CPU_NAME', 'amd_epyc')
compiler_exec = os.environ.get('CXX', 'c++')
dace.config.Config.set("compiler", "cpu", "executable", value=compiler_exec)

# Base compilation flags
base_flags = [
    '-fopenmp', '-fstrict-aliasing', '-std=c++17', '-faligned-new',
    '-fPIC', '-Wall', '-Wextra', '-O3', '-march=native', 
    '-Wno-unused-parameter', '-Wno-unused-label', "-ffast-math",
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



# ---------------------------------------------------------------------------
# Data generator
# ---------------------------------------------------------------------------

def generate_autoconversion_snow_data() -> Dict[str, np.ndarray]:
    """
    Generate synthetic data for the autoconversion_snow routine.
    """

    # Species indices / sizes – align with scalar_specialization_values
    ncldqs_val = np.int32(4)  # snow index & 2nd dim size
    ncldqi_val = np.int32(2)  # ice index  & 3rd dim size

    # Scalars
    rtt         = np.float64(273.16)   # triple point
    rlcritsnow  = np.float64(1e-4)     # critical ice content for snow
    rsnowlin1   = np.float64(1.0e-3)   # linear coefficient 1
    rsnowlin2   = np.float64(0.05)     # linear coefficient 2 (1/K)
    rnice       = np.float64(1.0e7)    # reference ice number conc
    ptsphy      = np.float64(2.0)      # timestep [s]
    zepsec      = np.float64(1e-12)    # epsilon
    laericeauto = True                 # exercise aerosol-aware branch

    kidia = np.int32(1)
    kfdia = np.int32(klon_val)
    klon  = np.int32(klon_val)

    # ---- 1D fields (length = KLON) ----
    # Temperature: some below RTT, some above
    ztp1 = np.linspace(250.0, 270.0, klon_val).astype(np.float64)

    # Ice cloud water (must be > zepsec in many points to trigger kernel)
    zicecld = (1e-5 + 5e-4 * np.random.rand(klon_val)).astype(np.float64)

    # Ice number concentration: positive, around RNICE
    pnice = (0.5 * rnice + 1.5 * rnice * np.random.rand(klon_val)).astype(np.float64)

    # ---- 3D source / sink tensor ----
    # Dimensions: (KFDIA, NCLDQS, NCLDQI)
    zsolqb = np.zeros((klon_val, int(ncldqs_val), int(ncldqi_val)), dtype=np.float64)

    # ---- Output snow autoconversion ----
    zsnowaut = np.zeros(klon_val, dtype=np.float64)
    timer = np.zeros((2,), dtype=np.float64)

    return dict(
        kidia=kidia,
        kfdia=kfdia,
        klon=klon,
        ztp1=ztp1,
        zicecld=zicecld,
        pnice=pnice,
        zsolqb=zsolqb,
        zsnowaut=zsnowaut,
        rtt=rtt,
        rlcritsnow=rlcritsnow,
        rsnowlin1=rsnowlin1,
        rsnowlin2=rsnowlin2,
        rnice=rnice,
        ptsphy=ptsphy,
        zepsec=zepsec,
        laericeauto=laericeauto,
        ncldqs=ncldqs_val,
        ncldqi=ncldqi_val,
        timer=timer,
        sym_klon=klon_val,
        sym_klev=klev_val
    )

# ---------------------------------------------------------------------------
# Fortran compilation and wrapper
# ---------------------------------------------------------------------------

def compile_autoconversion_snow_fortran(
    src_path: str = "./autoconversion_snow.f90",
    libname: str = "libautoconversion_snow.so",
    func_name: str = "autoconversion_snow",
):
    """
    Compile the autoconversion_snow Fortran routine into a shared library
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

    if cxx.endswith("clang++"):
        cmd = [f90, "-O3",  "-fPIC", "-shared", "-ffast-math",  src_path, "-o", libname]
    else:
        cmd = [f90, "-O3",  "-fPIC", "-shared", "-ffast-math", "-fno-math-errno", src_path, "-o", libname]
    print("Compiling Fortran:", " ".join(cmd))
    subprocess.check_call(cmd)
    print(f"Built {libname}")

    lib = ctypes.CDLL(f"./{libname}")
    try:
        func = getattr(lib, func_name)
    except AttributeError:
        raise RuntimeError(f"Fortran symbol '{func_name}' not found in shared library.")

    ndF64_1d = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags="F_CONTIGUOUS")
    ndF64_3d = np.ctypeslib.ndpointer(dtype=np.float64, ndim=3, flags="F_CONTIGUOUS")

    func.restype = None
    func.argtypes = [
        ctypes.c_int,   # KIDIA
        ctypes.c_int,   # KFDIA
        ctypes.c_int,   # KLON
        ndF64_1d,       # ZTP1
        ndF64_1d,       # ZICECLD
        ndF64_1d,       # PNICE
        ndF64_3d,       # ZSOLQB
        ndF64_1d,       # ZSNOWAUT
        ctypes.c_double,  # RTT
        ctypes.c_double,  # RLCRITSNOW
        ctypes.c_double,  # RSNOWLIN1
        ctypes.c_double,  # RSNOWLIN2
        ctypes.c_double,  # RNICE
        ctypes.c_double,  # PTSPHY
        ctypes.c_double,  # ZEPSEC
        ctypes.c_bool,    # LAERICEAUTO
        ctypes.c_int,     # NCLDQS
        ctypes.c_int,     # NCLDQI
        ndF64_1d, # timer
    ]

    print("Fortran function loaded (autoconversion_snow)")
    return func

def wrap_autoconversion_snow(func):
    """
    Thin wrapper to call the Fortran autoconversion_snow routine
    using a kwargs dict consistent with the Python/DaCe naming.
    """
    arg_order = [
        "kidia", "kfdia", "klon",
        "ztp1", "zicecld", "pnice",
        "zsolqb", "zsnowaut",
        "rtt", "rlcritsnow", "rsnowlin1", "rsnowlin2", "rnice",
        "ptsphy", "zepsec", "laericeauto",
        "ncldqs", "ncldqi", "timer"
    ]

    def wrapper(**kwargs):
        args = [kwargs[name] for name in arg_order]
        return func(*args)

    return wrapper

# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

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


def run_autoconversion_snow():
    # ----- Generate Inputs -----
    data = generate_autoconversion_snow_data()
    # Prepare Fortran/DaCe copies (Fortran wants F-contiguous for multi-d arrays)
    data_F_dace     = make_col_major(data)  # you already have this helper
    data_F          = make_col_major(data)


    # ----- Build SDFG -----
    sdfg = dace.SDFG.from_file("autoconversion_snow.sdfg")
    sdfg.name = "autoconversion_snow"

    # Optional preprocessing passes (same as your other runners)
    from dace.transformation.passes.vectorization.tasklet_preprocessing_passes import (
        PowerOperatorExpansion,
        RemoveFPTypeCasts,
        RemoveIntTypeCasts,
    )
    PowerOperatorExpansion().apply_pass(sdfg, {})
    RemoveFPTypeCasts().apply_pass(sdfg, {})
    RemoveIntTypeCasts().apply_pass(sdfg, {})
    OffsetLoopsAndMaps(offset_expr="-1", begin_expr=None).apply_pass(sdfg, {})
    # Specialize scalars from scalar_specialization_values if relevant
    for scalar_name, scalar_value in scalar_specialization_values.items():
        if scalar_name in sdfg.arrays:
            sdutil.specialize_scalar(
                sdfg=sdfg, scalar_name=scalar_name, scalar_val=scalar_value
            )
            sdfg.validate()
        if scalar_name in sdfg.symbols:
            sdfg.replace_dict({scalar_name: scalar_value})
            sdfg.remove_symbol(scalar_name)
    repldict = {"sym_nclv": 5,
                "sym_ncldqs": scalar_specialization_values["ncldqs"],
                "sym_ncldqi": scalar_specialization_values["ncldqi"],
                "sym_ncldqs": scalar_specialization_values["ncldqs"],
                "sym_ncldqv": scalar_specialization_values["ncldqv"]}
    sdfg.replace_dict(repldict)
    for sym, val in repldict.items():
        if sym in sdfg.symbols:
            sdfg.remove_symbol(sym)
    sdfg.validate()
    RemoveUnusedSymbols().apply_pass(sdfg, {})
    ConstantPropagation().apply_pass(sdfg, {})
    sdfg.apply_transformations_repeated(LoopToMap)
    sdfg.simplify()
    sdfg.instrument = dace.dtypes.InstrumentationType.Timer

    sdfg.simplify()
    set_map_sched(sdfg)

    compiled = sdfg.compile()

    # Run DaCe version
    compiled(**data_F_dace)
    report = sdfg.get_latest_report()
    dace_total_time = report.events[0].duration  # useconds
    print(f"Run time SDFG ({sdfg.name}): {float(dace_total_time)} us")
    write_runtime(f"autoconversion_snow{env_suffix_str}_v3", "dace", dace_total_time)

    # ----- Build and run Fortran -----
    raw_func = compile_autoconversion_snow_fortran(
        "./autoconversion_snow_w_timer.f90",
        "libautoconversion_snow.so",
        "autoconversion_snow",
    )
    fortran_func = wrap_autoconversion_snow(raw_func)
    fortran_func(**data_F)
    fortran_total_time = float(data_F["timer"][0])
    print(f"Run time Fortran: {fortran_total_time} us")
    write_runtime(f"autoconversion_snow{env_suffix_str}_v3", "fortran", fortran_total_time)

    # ----- Results -----
    print("Autoconversion snow (DaCe vs Fortran) comparison:")
    if compare_row_col_dicts(data_F_dace, data_F, rtol=1e-12, atol=1e-12):
        for rep in range(10):
            compiled(**data_F_dace)
            report = sdfg.get_latest_report()
            dace_time = report.events[0].duration

            print(f"  Run DaCe {rep+1}/10: {dace_time} us")

            write_runtime(
                f"autoconversion_snow{env_suffix_str}_v3",
                "dace",
                dace_time,
            )
    del data_F_dace
    copy_data_F = copy.deepcopy(data_F)
    for rep in range(10):
        fortran_func(**copy_data_F)
        fortran_total_time = float(copy_data_F["timer"][0])
        print(f"  Run time Fortran {rep+1}/10: {fortran_total_time} us")
        write_runtime(
            f"autoconversion_snow{env_suffix_str}_v3",
            "fortran",
            fortran_total_time,
        )
    del copy_data_F

    if cpu_name == "intel_xeon":
        vlens = [8, 16, 32, 64]
    elif cpu_name == "amd_epyc":
        vlens = [4, 8, 16, 32, 64]
    else:
        vlens = [2, 4, 8, 16, 32, 64]
    
    for vlen in vlens:
        for cpy in [False, True]:
            data_F_dace_vec = make_col_major(data)
            vec_sdfg = copy.deepcopy(sdfg)
            vec_sdfg.name = vec_sdfg.name + "_vectorized"

            eb = EliminateBranches()
            eb.try_clean = True
            eb.apply_pass(vec_sdfg, {})
            ConstantPropagation().apply_pass(vec_sdfg, {})
            RemoveUnusedSymbols().apply_pass(vec_sdfg, {})
            VectorizeCPU(vector_width=vlen, try_to_demote_symbols_in_nsdfgs=True,
                        fuse_overlapping_loads=False, insert_copies=cpy,
                        eliminate_trivial_vector_map=True).apply_pass(vec_sdfg, {})
            set_map_sched(vec_sdfg)
            vec_sdfg.save(f"ice_supersaturation_{vlen}.sdfg")

            vec_compiled = vec_sdfg.compile()
            # Run DaCe version
            vec_compiled(**data_F_dace_vec)
            report = vec_sdfg.get_latest_report()
            dace_total_time = report.events[0].duration  # useconds
            print(f"Run time SDFG ({vec_sdfg.name}): {float(dace_total_time)} us")
            if compare_row_col_dicts(data_F_dace_vec, data_F, rtol=1e-12, atol=1e-12):
                write_runtime(f"autoconversion_snow{env_suffix_str}_v3", "dace_vec", dace_total_time, vlen=vlen, cpy=cpy)

                for rep in range(10):
                    vec_compiled(**data_F_dace_vec)
                    report = vec_sdfg.get_latest_report()
                    dace_vec_time = report.events[0].duration
                    print(f"  Run {rep+1}/10: {dace_vec_time} us")
                    write_runtime(
                        f"autoconversion_snow{env_suffix_str}_v3",
                        "dace_vec",
                        dace_vec_time,
                        vlen=vlen,
                        cpy=cpy,
                    )


if __name__ == "__main__":
    run_autoconversion_snow()
