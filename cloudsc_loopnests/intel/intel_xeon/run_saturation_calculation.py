"""
Saturation Values Calculation - DaCe Version
"""

import copy
from typing import Any, Dict
import dace
import math
import numpy as np
from dace.properties import CodeBlock
from dace.sdfg.state import ConditionalBlock
import dace.sdfg.utils as sdutil
import subprocess
import ctypes
import os
from typing import Callable
from math import exp, log, pow

from dace.transformation.interstate.loop_to_map import LoopToMap
from dace.transformation.passes import ConstantPropagation, EliminateBranches, OffsetLoopsAndMaps
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

def generate_compute_saturation_values_data():
    # Scalars
    rtt = np.float64(273.16)
    retv = np.float64(0.608)
    r2es = np.float64(611.21)
    r3les = np.float64(17.502)
    r3ies = np.float64(22.587)
    r4les = np.float64(32.19)
    r4ies = np.float64(-0.7)
    rtice = np.float64(250.0)
    rtwat = np.float64(273.16)
    rtwat_rtice_r = np.float64(1.0 / (rtwat - rtice))

    # Input fields
    ztp1 = np.linspace(220, 310, klev_val * klon_val).reshape(klev_val, klon_val).astype(np.float64)
    pap  = np.linspace(1000, 10000, klev_val * klon_val).reshape(klev_val, klon_val).astype(np.float64)

    # Output fields
    zfoealfa   = np.zeros((klev_val, klon_val), dtype=np.float64)
    zqsmix     = np.zeros((klev_val, klon_val), dtype=np.float64)
    zfoeew     = np.zeros((klev_val, klon_val), dtype=np.float64)
    zqsice     = np.zeros((klev_val, klon_val), dtype=np.float64)
    zfoeeliqt  = np.zeros((klev_val, klon_val), dtype=np.float64)
    zqsliq     = np.zeros((klev_val, klon_val), dtype=np.float64)
    zfoeewmt   = np.zeros((klev_val, klon_val), dtype=np.float64)
    timer   = np.zeros((2), dtype=np.float64)

    # Pack everything into a dict to call compiled SDFG directly
    return dict(
        ztp1=ztp1,
        pap=pap,
        zfoealfa=zfoealfa,
        zqsmix=zqsmix,
        zfoeew=zfoeew,
        zqsice=zqsice,
        zfoeeliqt=zfoeeliqt,
        zqsliq=zqsliq,
        zfoeewmt=zfoeewmt,
        rtt=rtt,
        retv=retv,
        r2es=r2es,
        r3les=r3les,
        r3ies=r3ies,
        r4les=r4les,
        r4ies=r4ies,
        rtice=rtice,
        rtwat=rtwat,
        rtwat_rtice_r=rtwat_rtice_r,
        klon=np.int32(klon_val),
        klev=np.int32(klev_val),
        kidia=np.int32(1),
        kfdia=np.int32(klon_val),
        timer=timer
    )

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

def compile_fortran(src_path: str = "./saturation_calculation.f90",
                    libname: str = "libsaturation.so",
                    func_name: str = "compute_saturation_values") -> Callable:
    """
    Compile a Fortran file into a shared library and return a Python-callable
    wrapper for the compute_saturation_values subroutine.

    Parameters
    ----------
    src_path : str
        Path to the .f90 source file.
    libname : str
        Output shared library name.

    Returns
    -------
    compute_sat : Python wrapper for the Fortran subroutine
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

    # Load the shared library
    lib = ctypes.CDLL(f"./{libname}")

    # Fortran symbol name (“compute_saturation_values_”)
    symbol = func_name
    try:
        compute_sat = getattr(lib, symbol)
    except AttributeError:
        raise RuntimeError(f"Fortran symbol '{symbol}' not found in shared library.")

    compute_sat.restype = None

    # Build ctypes argtypes directly (same as earlier)
    ndF64 = np.ctypeslib.ndpointer(dtype=np.float64, flags='F_CONTIGUOUS')

    compute_sat.argtypes = [
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, # KIDIA, KFDIA, klon, klev
        ndF64, ndF64,                                     # ZTP1, PAP
        ndF64, ndF64, ndF64, ndF64, ndF64, ndF64, ndF64,  # ZFOEALFA .. ZQSLIQ
        ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
        ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
        ctypes.c_double, ctypes.c_double,                  # RTT..RTWAT_RTICE_R
        ndF64, # Timer
    ]

    print("Fortran function loaded")

    return compute_sat

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

def wrap_saturation_calculation(func):
    arg_order = [
        "KIDIA", "KFDIA", "KLON", "KLEV", "ZTP1", "PAP",
        "ZFOEALFA", "ZFOEEWMT", "ZQSMIX", "ZFOEEW",
        "ZQSICE", "ZFOEELIQT", "ZQSLIQ", "RTT",
        "RETV", "R2ES", "R3LES", "R3IES", "R4LES",
        "R4IES", "RTICE", "RTWAT", "RTWAT_RTICE_R",
        "TIMER"
    ]

    def wrapper(**kwargs):
        args = [kwargs[name.lower()] for name in arg_order]
        return func(*args)

    return wrapper

"""
Saturation Values Calculation - DaCe Version
"""

import copy
from typing import Any, Dict
import dace
import math
import numpy as np
from dace.properties import CodeBlock
from dace.sdfg.state import ConditionalBlock
import dace.sdfg.utils as sdutil
import subprocess
import ctypes
import os
from typing import Callable
from math import exp, log, pow

from dace.transformation.interstate.loop_to_map import LoopToMap
from dace.transformation.passes import ConstantPropagation, EliminateBranches, OffsetLoopsAndMaps
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
klev_val = _read_env_int("__DACE_KLEV", 8)
klon_val = _read_env_int("__DACE_KLON", 8192*1024)
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

def generate_compute_saturation_values_data():
    # Scalars
    rtt = np.float64(273.16)
    retv = np.float64(0.608)
    r2es = np.float64(611.21)
    r3les = np.float64(17.502)
    r3ies = np.float64(22.587)
    r4les = np.float64(32.19)
    r4ies = np.float64(-0.7)
    rtice = np.float64(250.0)
    rtwat = np.float64(273.16)
    rtwat_rtice_r = np.float64(1.0 / (rtwat - rtice))

    # Input fields
    ztp1 = np.linspace(220, 310, klev_val * klon_val).reshape(klev_val, klon_val).astype(np.float64)
    pap  = np.linspace(1000, 10000, klev_val * klon_val).reshape(klev_val, klon_val).astype(np.float64)

    # Output fields
    zfoealfa   = np.zeros((klev_val, klon_val), dtype=np.float64)
    zqsmix     = np.zeros((klev_val, klon_val), dtype=np.float64)
    zfoeew     = np.zeros((klev_val, klon_val), dtype=np.float64)
    zqsice     = np.zeros((klev_val, klon_val), dtype=np.float64)
    zfoeeliqt  = np.zeros((klev_val, klon_val), dtype=np.float64)
    zqsliq     = np.zeros((klev_val, klon_val), dtype=np.float64)
    zfoeewmt   = np.zeros((klev_val, klon_val), dtype=np.float64)
    timer   = np.zeros((2), dtype=np.float64)

    # Pack everything into a dict to call compiled SDFG directly
    return dict(
        ztp1=ztp1,
        pap=pap,
        zfoealfa=zfoealfa,
        zqsmix=zqsmix,
        zfoeew=zfoeew,
        zqsice=zqsice,
        zfoeeliqt=zfoeeliqt,
        zqsliq=zqsliq,
        zfoeewmt=zfoeewmt,
        rtt=rtt,
        retv=retv,
        r2es=r2es,
        r3les=r3les,
        r3ies=r3ies,
        r4les=r4les,
        r4ies=r4ies,
        rtice=rtice,
        rtwat=rtwat,
        rtwat_rtice_r=rtwat_rtice_r,
        klon=np.int32(klon_val),
        klev=np.int32(klev_val),
        kidia=np.int32(1),
        kfdia=np.int32(klon_val),
        timer=timer
    )

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

def wrap_saturation_calculation(func):
    arg_order = [
        "KIDIA", "KFDIA", "KLON", "KLEV", "ZTP1", "PAP",
        "ZFOEALFA", "ZFOEEWMT", "ZQSMIX", "ZFOEEW",
        "ZQSICE", "ZFOEELIQT", "ZQSLIQ", "RTT",
        "RETV", "R2ES", "R3LES", "R3IES", "R4LES",
        "R4IES", "RTICE", "RTWAT", "RTWAT_RTICE_R",
        "TIMER"
    ]

    def wrapper(**kwargs):
        args = [kwargs[name.lower()] for name in arg_order]
        return func(*args)

    return wrapper

def run_saturation_calculation():
    # ===== Generate Inputs =====
    base_data       = generate_compute_saturation_values_data()
    data_F          = make_col_major(copy.deepcopy(base_data))
    data_F_dace     = make_col_major(copy.deepcopy(base_data))

    # ===== Build SDFG =====
    sdfg = dace.SDFG.from_file("saturation_calculation.sdfg")
    sdfg.name = "saturation_calculation"

    # Offset loops once at the beginning
    OffsetLoopsAndMaps(offset_expr="-1", begin_expr=None).apply_pass(sdfg, {})

    from dace.transformation.passes.vectorization.tasklet_preprocessing_passes import (
        PowerOperatorExpansion,
        RemoveFPTypeCasts,
        RemoveIntTypeCasts,
    )

    # Preprocessing
    PowerOperatorExpansion().apply_pass(sdfg, {})
    RemoveFPTypeCasts().apply_pass(sdfg, {})
    RemoveIntTypeCasts().apply_pass(sdfg, {})

    # ----- Specialize scalars from scalar_specialization_values -----
    for scalar_name, scalar_value in scalar_specialization_values.items():
        if scalar_name in sdfg.arrays:
            sdutil.specialize_scalar(
                sdfg=sdfg, scalar_name=scalar_name, scalar_val=scalar_value
            )
            sdfg.validate()
        if scalar_name in sdfg.symbols:
            sdfg.replace_dict({scalar_name: scalar_value})
            sdfg.remove_symbol(scalar_name)

    # Replace known symbolic constants
    repldict = {
        "sym_nclv": 5,
        "sym_klon": klon_val,
        "sym_klev": klev_val,
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
    sdfg.save("saturation_calculation_simpl.sdfg")

    # Parallelization + instrumentation
    sdfg.apply_transformations_repeated(LoopToMap)
    sdfg.instrument = dace.dtypes.InstrumentationType.Timer
    sdfg.simplify()
    set_map_sched(sdfg)
    sdfg.save("saturation_calculation_par.sdfg")

    # ===== Compile and run DaCe baseline (1×) =====
    compiled = sdfg.compile()
    compiled(**data_F_dace)

    report = sdfg.get_latest_report()
    dace_total_time = report.events[0].duration  # microseconds
    print(f"Run time SDFG ({sdfg.name}): {float(dace_total_time)} us")
    write_runtime(f"saturation_calculation{env_suffix_str}_v3", "dace", dace_total_time)

    # ===== Build and run Fortran baseline (1×) =====
    raw_func = compile_fortran(
        "./saturation_calculation_w_timer.f90",
        "libsaturation.so",
        "compute_saturation_values",
    )
    fortran_func = wrap_saturation_calculation(raw_func)
    fortran_func(**data_F)

    fortran_total_time = float(data_F["timer"][0])
    print(f"Run time Fortran: {fortran_total_time} us")
    write_runtime(f"saturation_calculation{env_suffix_str}_v3", "fortran", fortran_total_time)

    # ===== Baseline results + repeated timings =====
    print("Saturation calculation (DaCe vs Fortran) comparison:")
    if compare_row_col_dicts(data_F_dace, data_F, rtol=1e-13, atol=1e-12):
        # 10× repeated DaCe baseline on mutated data_F_dace
        for rep in range(10):
            compiled(**data_F_dace)
            report = sdfg.get_latest_report()
            dace_time = report.events[0].duration
            print(f"  Run DaCe {rep+1}/10: {dace_time} us")
            write_runtime(
                f"saturation_calculation{env_suffix_str}_v3",
                "dace",
                dace_time,
            )

    del data_F_dace

    # 10× repeated Fortran baseline on a fresh copy
    fortran_repeat_data = make_col_major(copy.deepcopy(base_data))
    for rep in range(10):
        fortran_func(**fortran_repeat_data)
        ft_time = float(fortran_repeat_data["timer"][0])
        print(f"  Run Fortran {rep+1}/10: {ft_time} us")
        write_runtime(
            f"saturation_calculation{env_suffix_str}_v3",
            "fortran",
            ft_time,
        )

    # ===== Clean branch in nested SDFG (as in your original code) =====
    for state in sdfg.all_states():
        for node in state.nodes():
            if isinstance(node, dace.nodes.NestedSDFG):
                inner_sdfg = node.sdfg
                for inner_node in inner_sdfg.nodes():
                    if isinstance(inner_node, ConditionalBlock):
                        for cond, branch in inner_node.branches:
                            for inner_state in branch.nodes():
                                dnodes = inner_state.data_nodes()
                                d = {dnode.data for dnode in dnodes}
                                if "tmp_call_0" in d:
                                    dnode = {
                                        dnode
                                        for dnode in inner_state.data_nodes()
                                        if dnode.data == "tmp_call_0"
                                    }.pop()
                                    for ie in inner_state.in_edges(dnode):
                                        inner_state.remove_node(ie.src)
                                    for oe in inner_state.out_edges(dnode):
                                        oe.dst.code = CodeBlock("tmp_call_6_out = (- 1.0)")
                                        for inc in list(oe.dst.in_connectors.keys()):
                                            oe.dst.remove_in_connector(inc)
                                    inner_state.remove_node(dnode)

    # ===== Vectorization sweep (same pattern as others) =====
    if cpu_name == "intel_xeon":
        vlens = [8, 16, 32, 64]
    elif cpu_name == "amd_epyc":
        vlens = [4, 8, 16, 32, 64]
    else:
        vlens = [2, 4, 8, 16, 32, 64]

    for vlen in vlens:
        for cpy in [True, False]:
            # First vec run: fresh inputs from base_data
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
            dace_vec_time = report.events[0].duration  # microseconds

            print("Saturation calculation (DaCe-Vec vs Fortran) comparison:")
            if compare_row_col_dicts(
                data_F_dace_vec, data_F, rtol=1e-13, atol=1e-12
            ):
                print(
                    f"Run time SDFG ({vec_sdfg.name}): {float(dace_vec_time)} us"
                )
                write_runtime(
                    f"saturation_calculation{env_suffix_str}_v3",
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
                        f"saturation_calculation{env_suffix_str}_v3",
                        "dace_vec",
                        dace_vec_time_rep,
                        vlen=vlen,
                        cpy=cpy,
                    )


if __name__ == "__main__":
    run_saturation_calculation()