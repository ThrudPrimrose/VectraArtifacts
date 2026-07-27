"""Canonical compiler-flag matrix.

Encodes the per-compiler, per-cost-model flag sets documented in
``docs/VECTORIZATION_FLAGS.md`` so build scripts, source.sh emitters, and
DaCe-config wiring all share one ground truth.

Three compilers, three cost models, plus a math-call vectorization
opt-in: 3 * 3 * 2 = 18 :class:`FlagSet` instances. Each :class:`FlagSet`
holds compile flags + link flags + a short rationale string.

Width preference scales with target CPU's max usable vector width (512 on
AVX-512 hosts, 256 on AVX2-only); :func:`vector_width_for_cpu` resolves
the per-CPU value from a small lookup table or the ``VEC_WIDTH`` env var.
"""
from __future__ import annotations

import enum
import os
import platform
import subprocess
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple


class Compiler(enum.Enum):
    """The three supported compilers."""
    CLANG = "clang"
    GCC   = "gcc"
    ICPX  = "icpx"

    def executable(self) -> str:
        return EXECUTABLE_BY_COMPILER[self]


class CostModel(enum.Enum):
    """The three cost-model presets exercised by the perf grid."""
    DEFAULT   = "default"
    CHEAP     = "cheap"
    UNLIMITED = "unlimited"
    DISABLED  = "disabled"


class ArmAutovecPreference(enum.Enum):
    DEFAULT      = "default"
    ASIMD_ONLY   = "asimd-only"
    SVE_ONLY     = "sve-only"
    PREFER_ASIMD = "prefer-asimd"
    PREFER_SVE   = "prefer-sve"


EXECUTABLE_BY_COMPILER: Dict[Compiler, str] = {
    Compiler.CLANG: "clang++",
    Compiler.GCC:   "g++",
    Compiler.ICPX:  "icpx",
}


def _openmp_compile_flags(compiler: Compiler) -> Tuple[str, ...]:
    if compiler is Compiler.ICPX:
        return ("-fiopenmp",)
    if platform.system() == "Darwin":
        if compiler is Compiler.GCC:
            return ("-fopenmp",)
        try:
            prefix = subprocess.check_output(
                ["brew", "--prefix", "libomp"], text=True,
                stderr=subprocess.DEVNULL
            ).strip()
            return ("-Xclang", "-fopenmp", f"-I{prefix}/include")
        except Exception:
            return ()
    return ("-fopenmp",)


def _openmp_link_flags(compiler: Compiler) -> Tuple[str, ...]:
    if compiler is Compiler.ICPX:
        return ("-fiopenmp",)
    if platform.system() == "Darwin":
        if compiler is Compiler.GCC:
            return ("-fopenmp",)
        try:
            prefix = subprocess.check_output(
                ["brew", "--prefix", "libomp"], text=True,
                stderr=subprocess.DEVNULL
            ).strip()
            return (f"-L{prefix}/lib", "-lomp")
        except Exception:
            return ()
    return ("-fopenmp",)


BASELINE_FLAGS: Tuple[str, ...] = (
    "-O3",
    "-std=c++17",
    "-fPIC",
    "-ffast-math",
    "-fno-math-errno",
    "-fstrict-aliasing",
    "-faligned-new",
)

LINK_BASE_FLAGS: Tuple[str, ...] = ("-shared",)

_DELTAS: Dict[Tuple[Compiler, CostModel], Tuple[str, ...]] = {
    (Compiler.CLANG, CostModel.DEFAULT):   (),
    (Compiler.CLANG, CostModel.CHEAP):     ("-mprefer-vector-width=__VEC_WIDTH__",),
    (Compiler.CLANG, CostModel.UNLIMITED): ("-fvectorize", "-fvect-cost-model=none"),
    (Compiler.CLANG, CostModel.DISABLED):  ("-fno-vectorize", "-fno-slp-vectorize"),

    (Compiler.GCC, CostModel.DEFAULT):   (),
    (Compiler.GCC, CostModel.CHEAP):     ("-mprefer-vector-width=__VEC_WIDTH__",),
    (Compiler.GCC, CostModel.UNLIMITED): ("-ftree-vectorize", "-fvect-cost-model=unlimited"),
    (Compiler.GCC, CostModel.DISABLED):  ("-fno-tree-vectorize", "-fno-tree-slp-vectorize"),

    (Compiler.ICPX, CostModel.DEFAULT):   (),
    (Compiler.ICPX, CostModel.CHEAP):     ("__ICPX_WIDTH_FLAG__",),
    (Compiler.ICPX, CostModel.UNLIMITED): ("-vec", "-qopt-zmm-usage=high"),
    (Compiler.ICPX, CostModel.DISABLED):  ("-no-vec", "-no-simd"),
}

_MATH_FLAGS: Dict[Compiler, Tuple[str, ...]] = {
    Compiler.CLANG: () if platform.system() == "Darwin" else ("-fveclib=libmvec",),
    Compiler.GCC:   (),
    Compiler.ICPX:  (),
}

_CPU_VEC_WIDTH_FALLBACK: Dict[str, int] = {
    "intel_xeon":      512,
    "amd_epyc":        256,
    "amd_epyc_genoa":  512,
    "arm":             128,
    "arm_grace":       128,
    "ibm_power":       128,
    "fugaku_a64fx":    512,
}

_SVE_BITS_CACHE: Dict[str, int] = {"value": -1}

_ICPX_WIDTH_FLAG_FOR_WIDTH: Dict[int, str] = {
    512: "-qopt-zmm-usage=high",
    256: "-qopt-ymm-usage=high",
    128: "-qopt-ymm-usage=high",
}

# ── Vectorization remark flags ─────────────────────────────────────────────────
# Purely diagnostic — never affect vectorization decisions.
# Output goes to stderr. GCC supports -fopt-info-vec=<file> for per-file
# redirection; Clang saves a YAML opt-record via -fsave-optimization-record.

_REMARK_FLAGS: Dict[Compiler, Tuple[str, ...]] = {
    Compiler.CLANG: (
        "-Rpass=loop-vectorize",
        "-Rpass-missed=loop-vectorize",
        "-Rpass-analysis=loop-vectorize",
    ),
    Compiler.GCC: (
        "-fopt-info-vec-optimized",
        "-fopt-info-vec-missed",
    ),
    Compiler.ICPX: (
        "-Rpass=loop-vectorize",
        "-Rpass-missed=loop-vectorize",
        "-qopt-report=5",
        "-qopt-report-phase=vec",
    ),
}

# Templates for redirecting remarks to a file (use {path} placeholder)
_REMARK_FILE_FLAGS: Dict[Compiler, str] = {
    Compiler.GCC:   "-fopt-info-vec={path}",
    Compiler.CLANG: "-fsave-optimization-record -foptimization-record-file={path}",
    Compiler.ICPX:  "-qopt-report-file={path}",
}


def get_remark_flags(
    compiler: Compiler,
    output_file: Optional[str] = None,
) -> Tuple[str, ...]:
    """
    Return vectorization remark flags for *compiler*.

    These flags are purely observational and should be appended to the
    compile flags from :func:`get_flags` when capturing a vec report.
    Remarks go to stderr unless *output_file* is specified.

    Args:
        compiler:    Target compiler.
        output_file: Optional path to redirect remark output to a file.
                     If None, remarks go to stderr.
    """
    flags = list(_REMARK_FLAGS[compiler])
    if output_file is not None:
        template = _REMARK_FILE_FLAGS.get(compiler)
        if template:
            for part in template.format(path=output_file).split():
                flags.append(part)
    return tuple(flags)


def _read_cpuinfo_flags() -> List[str]:
    try:
        with open("/proc/cpuinfo", "r") as fh:
            text = fh.read()
    except OSError:
        return []
    seen: set = set()
    for line in text.splitlines():
        if line.startswith(("flags", "Features")):
            _, _, rhs = line.partition(":")
            for tok in rhs.split():
                seen.add(tok)
    return sorted(seen)


def _sve_bits_from_proc() -> int:
    if _SVE_BITS_CACHE["value"] != -1:
        return _SVE_BITS_CACHE["value"]
    bits = 0
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        PR_SVE_GET_VL = 51
        ret = libc.prctl(PR_SVE_GET_VL, 0, 0, 0, 0)
        if ret > 0:
            bits = (ret & 0xFFFF) * 8
    except Exception:
        bits = 0
    _SVE_BITS_CACHE["value"] = bits
    return bits


def detect_local_vector_width(default: int = 256) -> int:
    override = os.environ.get("VEC_WIDTH")
    if override and override.isdigit():
        return int(override)
    flags = _read_cpuinfo_flags()
    if "sve" in flags:
        bits = _sve_bits_from_proc()
        if bits > 0:
            return bits
    if "avx512f" in flags:
        return 512
    if "avx2" in flags or "avx" in flags:
        return 256
    if "sse2" in flags or "sse" in flags:
        return 128
    if "asimd" in flags or "neon" in flags:
        return 128
    if "altivec" in flags or "vsx" in flags:
        return 128
    return default


def vector_width_for_cpu(cpu: Optional[str], default: int = 256) -> int:
    override = os.environ.get("VEC_WIDTH")
    if override and override.isdigit():
        return int(override)
    if cpu is None or cpu == "local":
        return detect_local_vector_width(default=default)
    if cpu in _CPU_VEC_WIDTH_FALLBACK:
        return _CPU_VEC_WIDTH_FALLBACK[cpu]
    return default


@dataclass(frozen=True)
class FlagSet:
    """Resolved flag set for a (compiler, cost-model, math) combination."""
    compiler:      Compiler
    cost_model:    CostModel
    math:          bool
    compile_flags: Tuple[str, ...]
    link_flags:    Tuple[str, ...]
    cpu:           Optional[str] = None
    arm_autovec:   Optional[ArmAutovecPreference] = None
    rationale:     str = ""

    def compile_flag_str(self) -> str:
        return " ".join(self.compile_flags)

    def link_flag_str(self) -> str:
        return " ".join(self.link_flags)

    def with_remark_flags(self, output_file: Optional[str] = None) -> "FlagSet":
        """Return a new FlagSet with vectorization remark flags appended."""
        extra = get_remark_flags(self.compiler, output_file=output_file)
        return FlagSet(
            compiler=self.compiler,
            cost_model=self.cost_model,
            math=self.math,
            compile_flags=self.compile_flags + extra,
            link_flags=self.link_flags,
            cpu=self.cpu,
            arm_autovec=self.arm_autovec,
            rationale=self.rationale,
        )


def _resolve_placeholders(flags: Iterable[str], cpu: Optional[str]) -> List[str]:
    width    = vector_width_for_cpu(cpu)
    icpx_flag = _ICPX_WIDTH_FLAG_FOR_WIDTH.get(width, "-qopt-zmm-usage=high")
    out: List[str] = []
    for f in flags:
        if "__VEC_WIDTH__" in f:
            out.append(f.replace("__VEC_WIDTH__", str(width)))
        elif "__ICPX_WIDTH_FLAG__" in f:
            out.append(icpx_flag)
        else:
            out.append(f)
    return out


_AARCH64_CPUS = frozenset(("arm", "arm_grace", "fugaku_a64fx", "apple_m_series"))


def _is_aarch64_cpu(cpu: Optional[str]) -> bool:
    if cpu is None:
        flags = _read_cpuinfo_flags()
        return any(f in flags for f in ("asimd", "neon", "sve"))
    return cpu in _AARCH64_CPUS


def _rationale_for(compiler: Compiler,
                   cost_model: CostModel,
                   math: bool,
                   arm_autovec: Optional[ArmAutovecPreference] = None) -> str:
    base = {
        (Compiler.CLANG, CostModel.DEFAULT):   "Clang -O3 baseline; paper Table 2 Default row + artifact additions.",
        (Compiler.CLANG, CostModel.CHEAP):     "Clang -mprefer-vector-width=N (no user-facing cheap knob; width hint = paper's next step down).",
        (Compiler.CLANG, CostModel.UNLIMITED): "Clang -O3 -fvectorize -fslp-vectorize -fvect-cost-model=none; vectorise whenever physically possible, profitability ignored.",
        (Compiler.CLANG, CostModel.DISABLED):  "Clang -fno-vectorize -fno-slp-vectorize; all SIMD generation suppressed (scalar baseline).",
        (Compiler.GCC,   CostModel.DEFAULT):   "GCC -O3 baseline (auto-vectorize implicit at -O3).",
        (Compiler.GCC,   CostModel.CHEAP):     "GCC -fvect-cost-model=cheap -fsimd-cost-model=cheap; lower profitability bar than default.",
        (Compiler.GCC,   CostModel.UNLIMITED): "GCC -ftree-vectorize -ftree-slp-vectorize -fvect-cost-model=unlimited; vectorise whenever physically possible, profitability ignored.",
        (Compiler.GCC,   CostModel.DISABLED):  "GCC -fno-tree-vectorize -fno-tree-slp-vectorize; all SIMD generation suppressed (scalar baseline).",
        (Compiler.ICPX,  CostModel.DEFAULT):   "icpx -O3 baseline (LLVM-based, accepts Clang-style flags).",
        (Compiler.ICPX,  CostModel.CHEAP):     "icpx -qopt-zmm-usage=high / -qopt-ymm-usage=high (replaces -mprefer-vector-width).",
        (Compiler.ICPX,  CostModel.UNLIMITED): "icpx -vec -qopt-zmm-usage=high; vectorise whenever physically possible, profitability ignored.",
        (Compiler.ICPX,  CostModel.DISABLED):  "icpx -no-vec -no-simd; all SIMD generation suppressed (scalar baseline).",
    }
    s = base[(compiler, cost_model)]
    if math:
        if compiler == Compiler.CLANG:
            s += " +math: -fveclib=libmvec for sin/cos/log/exp."
        elif compiler == Compiler.GCC:
            s += " +math: libmvec implicit on glibc; -mveclibabi=svml/acml available."
        else:
            s += " +math: SVML linked automatically by icpx at -O3 -ffast-math."
    if arm_autovec is not None and compiler is Compiler.GCC:
        s += f" +arm_autovec={arm_autovec.value} (GCC --param aarch64-autovec-preference; aarch64 only)."
    return s


def get_flags(compiler: Compiler,
              cost_model: CostModel,
              math: bool = False,
              cpu: Optional[str] = None,
              include_march_native: bool = True,
              arm_autovec: Optional[ArmAutovecPreference] = None,
              extra: Iterable[str] = ()) -> FlagSet:

    flags: List[str] = list(BASELINE_FLAGS)
    flags.extend(_openmp_compile_flags(compiler))
    if include_march_native and (cpu != "arm"):
        flags.append("-march=native")
    flags.extend(_DELTAS[(compiler, cost_model)])
    flags = _resolve_placeholders(flags, cpu)

    if _is_aarch64_cpu(cpu):
        if compiler is Compiler.CLANG:
            if cost_model is CostModel.CHEAP:
                flags = [f for f in flags if not f.startswith("-mprefer-vector-width")]
            elif cost_model is CostModel.UNLIMITED:
                flags = [f for f in flags if f != "-fvect-cost-model=none"]
                flags.extend(["-mllvm", "-force-vector-width=4"])
        elif compiler is Compiler.GCC:
            if cost_model is CostModel.CHEAP:
                flags = [
                    "-fvect-cost-model=cheap" if f.startswith("-mprefer-vector-width") else f
                    for f in flags
                ]

    if math:
        flags.extend(_MATH_FLAGS[compiler])

    if arm_autovec is not None and compiler is Compiler.GCC and _is_aarch64_cpu(cpu):
        flags.append(f"--param=aarch64-autovec-preference={arm_autovec.value}")

    flags.extend(extra)

    link_flags = tuple(list(LINK_BASE_FLAGS) + list(_openmp_link_flags(compiler)))

    return FlagSet(
        compiler=compiler,
        cost_model=cost_model,
        math=math,
        compile_flags=tuple(flags),
        link_flags=link_flags,
        cpu=cpu,
        arm_autovec=arm_autovec,
        rationale=_rationale_for(compiler, cost_model, math, arm_autovec),
    )


def iter_combinations(cpu: Optional[str] = None, math: bool = False) -> Iterable[FlagSet]:
    """Yield a FlagSet for every (compiler, cost-model) combo on one CPU."""
    for compiler in Compiler:
        for cm in CostModel:
            yield get_flags(compiler, cm, math=math, cpu=cpu)