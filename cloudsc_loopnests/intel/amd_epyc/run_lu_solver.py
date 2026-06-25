"""
Autoconversion Snow - DaCe vs Fortran Runner
"""

import copy
from typing import Dict
import dace
import numpy as np
import dace.sdfg.utils as sdutil
import subprocess
import ctypes
import os

from dace.transformation.dataflow import WCRToAugAssign
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
klon_val = int(_read_env_int("__DACE_KLON", 8192))

nclv_val = 5


cpu_name = os.environ.get('CPU_NAME', 'amd_epyc')
compiler_exec = os.environ.get('CXX', 'c++')
dace.config.Config.set("compiler", "cpu", "executable", value=compiler_exec)

# Base compilation flags
base_flags = [
    '-fopenmp', '-fstrict-aliasing', '-std=c++17', '-faligned-new',
    '-fPIC', '-Wall', '-Wextra', '-O3', '-march=native', 
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



# ---------------------------------------------------------------------------
# Data generator
# ---------------------------------------------------------------------------

def generate_lu_solver_microphysics_data():
    """
    Generate synthetic but numerically stable data for LU solver microphysics.
    """
    kidia = np.int32(1)
    kfdia = np.int32(klon_val)
    klon  = np.int32(klon_val)
    nclv  = np.int32(nclv_val)
    
    # Create well-conditioned matrices for each column
    # Shape will be (NCLV, NCLV, KLON) to match your C layout [5, 5, KLON]
    ZQLHS = 10 * np.random.rand(nclv_val, nclv_val, klon_val).astype(dtype=np.float64)
    """
    for jl in range(klon_val):
        # Generate a well-conditioned symmetric positive definite matrix
        # This ensures numerical stability for LU decomposition
        A = np.random.randn(nclv_val, nclv_val)
        # Make it symmetric positive definite: A^T * A + I
        M = A.T @ A + np.eye(nclv_val) * 2.0
        
        # Alternatively, use a diagonally dominant matrix (even more stable)
        # M = np.random.rand(nclv_val, nclv_val) * 0.1
        # np.fill_diagonal(M, np.random.rand(nclv_val) + nclv_val)
        ZQLHS[:, :, jl] = M
    """
    # RHS vector: shape (NCLV, KLON) to match your C layout [5, KLON]
    ZQXN = 10 * np.random.rand(nclv_val, klon_val).astype(np.float64)
    
    timer = np.zeros((2,), dtype=np.float64)
    
    return dict(
        kidia=kidia,
        kfdia=kfdia,
        klon=klon,
        nclv=nclv,
        zqlhs=ZQLHS,
        zqxn=ZQXN,
        timer=timer,
        sym_klon=klon_val,
        sym_klev=klev_val,
        sym_nclv=5,
        sym_kfdia=1,
        sym_ncldqs=scalar_specialization_values["ncldqs"],
        sym_ncldqi=scalar_specialization_values["ncldqi"],
        sym_ncldqv=scalar_specialization_values["ncldqv"],
    )

# ---------------------------------------------------------------------------
# Fortran compilation + wrapper
# ---------------------------------------------------------------------------

def compile_lu_solver_fortran(
    src_path: str = "./lu_solver.f90",
    libname: str = "liblu_solver_microphysics.so",
    func_name: str = "lu_solver_microphysics",
):
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

    cmd = [f90, "-O3",  "-fPIC", "-shared",  src_path, "-o", libname]
    print("Compiling Fortran:", " ".join(cmd))
    subprocess.check_call(cmd)
    print(f"Built {libname}")
    lib = ctypes.CDLL(f"./{libname}")

    try:
        func = getattr(lib, func_name)
    except AttributeError:
        raise RuntimeError(f"Fortran symbol '{func_name}' not found in shared library.")

    ndF64_3d = np.ctypeslib.ndpointer(dtype=np.float64, ndim=3, flags="F_CONTIGUOUS")
    ndF64_2d = np.ctypeslib.ndpointer(dtype=np.float64, ndim=2, flags="F_CONTIGUOUS")
    ndF64_1d = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags="F_CONTIGUOUS")

    func.restype = None
    func.argtypes = [
        ctypes.c_int,   # KIDIA
        ctypes.c_int,   # KFDIA
        ctypes.c_int,   # KLON
        ctypes.c_int,   # NCLV
        ndF64_3d,       # ZQLHS
        ndF64_2d,       # ZQXN,
        ndF64_1d, # timer
    ]

    print("Fortran function loaded (lu_solver_microphysics)")
    return func

def wrap_lu_solver(func):
    order = [
        "kidia", "kfdia", "klon", "nclv",
        "zqlhs", "zqxn", "timer"
    ]

    def wrapper(**kwargs):
        args = [kwargs[k] for k in order]
        return func(*args)

    return wrapper

def run_lu_solver_microphysics():

    # --- Generate inputs ---
    base_data = generate_lu_solver_microphysics_data()

    # Fortran + DaCe need F-contiguous arrays, keep base_data for re-use
    data_F      = make_col_major(copy.deepcopy(base_data))
    data_F_dace = make_col_major(copy.deepcopy(base_data))

    # --- Load SDFG ---
    sdfg = dace.SDFG.from_file("lu_solver.sdfg")
    sdfg.name = "lu_solver_microphysics"

    from dace.transformation.passes.vectorization.tasklet_preprocessing_passes import (
        PowerOperatorExpansion,
        RemoveFPTypeCasts,
        RemoveIntTypeCasts,
    )

    sdfg.save("lu_solver_unspecialized.sdfg")
    PowerOperatorExpansion().apply_pass(sdfg, {})
    RemoveFPTypeCasts().apply_pass(sdfg, {})
    RemoveIntTypeCasts().apply_pass(sdfg, {})

    sdfg.apply_transformations_repeated(WCRToAugAssign)
    OffsetLoopsAndMaps(offset_expr="-1", begin_expr=None).apply_pass(sdfg, {})
    sdfg.apply_transformations_repeated(LoopToMap)
    sdfg.simplify()

    # --- Specialize scalars / symbols ---
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
        "sym_kfdia": 1,
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
    ConstantPropagation().apply_pass(sdfg, {})
    sdfg.simplify()

    sdfg.instrument = dace.dtypes.InstrumentationType.Timer
    set_map_sched(sdfg)
    sdfg.save("lu_solver_propagated.sdfg")

    compiled = sdfg.compile()

    # --- Run DaCe baseline (1×) ---
    compiled(**data_F_dace)
    report = sdfg.get_latest_report()
    dace_total_time = report.events[0].duration  # microseconds
    print(f"Run time SDFG ({sdfg.name}): {float(dace_total_time)} us")
    write_runtime(f"lu_solver_microphysics{env_suffix_str}_v3", "dace", dace_total_time)

    # --- Compile and run Fortran baseline (1×) ---
    raw = compile_lu_solver_fortran(
        "./lu_solver_w_timer.f90",
        "liblu_solver_microphysics.so",
        "lu_solver_microphysics",
    )
    fort = wrap_lu_solver(raw)
    fort(**data_F)
    fortran_total_time = float(data_F["timer"][0])
    print(f"Run time Fortran: {fortran_total_time} us")
    write_runtime(f"lu_solver_microphysics{env_suffix_str}_v3", "fortran", fortran_total_time)

    # --- Compare baseline results + repeated timings ---
    print("LU microphysics (DaCe vs Fortran) comparison:")
    if compare_row_col_dicts(data_F_dace, data_F, rtol=1e-9, atol=1e-4):

        # 10× DaCe baseline (reuse mutated data_F_dace)
        for rep in range(10):
            compiled(**data_F_dace)
            report = sdfg.get_latest_report()
            dace_time = report.events[0].duration
            print(f"  Run DaCe {rep+1}/10: {dace_time} us")
            write_runtime(
                f"lu_solver_microphysics{env_suffix_str}_v3",
                "dace",
                dace_time,
            )

    del data_F_dace

    # 10× Fortran baseline on a fresh deep copy
    data_F_repeat = make_col_major(copy.deepcopy(base_data))
    for rep in range(10):
        fort(**data_F_repeat)
        ft_time = float(data_F_repeat["timer"][0])
        print(f"  Run Fortran {rep+1}/10: {ft_time} us")
        write_runtime(
            f"lu_solver_microphysics{env_suffix_str}_v3",
            "fortran",
            ft_time,
        )

    # --- Vectorization sweep ---
    if cpu_name == "intel_xeon":
        vlens = [8, 16, 32, 64]
    elif cpu_name == "amd_epyc":
        vlens = [4, 8, 16, 32, 64]
    else:
        vlens = [2, 4, 8, 16, 32, 64]

    for vlen in vlens:
        for cpy in [False, True]:
            # First vector run: fresh input from base_data
            data_F_dace_vec = make_col_major(copy.deepcopy(base_data))

            vec_sdfg = copy.deepcopy(sdfg)
            vec_sdfg.instrument = dace.dtypes.InstrumentationType.Timer
            vec_sdfg.name = f"{sdfg.name}_vectorized_v{vlen}_cpy{int(cpy)}"

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
            vec_sdfg.save(f"lu_solver_vec_v{vlen}_cpy{int(cpy)}.sdfg")

            vec_compiled = vec_sdfg.compile()
            vec_compiled(**data_F_dace_vec)

            report = vec_sdfg.get_latest_report()
            dace_vec_time = report.events[0].duration  # microseconds
            print("LU microphysics (DaCe-Vec vs Fortran) comparison:")

            if compare_row_col_dicts(
                data_F_dace_vec, data_F, rtol=1e-9, atol=1e-4
            ):
                print(
                    f"Run time SDFG ({vec_sdfg.name}): {float(dace_vec_time)} us"
                )
                write_runtime(
                    f"lu_solver_microphysics{env_suffix_str}_v3",
                    "dace_vec",
                    dace_vec_time,
                    vlen=vlen,
                    cpy=cpy,
                )

                # 10× extra vec runs using same mutated data_F_dace_vec
                for rep in range(10):
                    vec_compiled(**data_F_dace_vec)
                    report = vec_sdfg.get_latest_report()
                    dace_vec_time_rep = report.events[0].duration
                    print(f"  Run {rep+1}/10: {dace_vec_time_rep} us")
                    write_runtime(
                        f"lu_solver_microphysics{env_suffix_str}_v3",
                        "dace_vec",
                        dace_vec_time_rep,
                        vlen=vlen,
                        cpy=cpy,
                    )


if __name__ == "__main__":
    run_lu_solver_microphysics()
