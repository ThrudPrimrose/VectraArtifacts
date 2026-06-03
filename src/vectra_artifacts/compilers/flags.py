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
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple


class Compiler(enum.Enum):
    """The three supported compilers."""
    CLANG = "clang"  # llvm clang / clang++
    GCC = "gcc"  # gnu g++
    ICPX = "icpx"  # intel oneapi (LLVM-based)

    def executable(self) -> str:
        return EXECUTABLE_BY_COMPILER[self]


class CostModel(enum.Enum):
    """The three cost-model presets exercised by the perf grid."""
    DEFAULT = "default"  # -O3 baseline
    CHEAP = "cheap"  # lighter cost-model (width-hint or true cheap knob)
    NO = "no"  # vectorization disabled (-fno-vectorize etc.)


class ArmAutovecPreference(enum.Enum):
    """GCC ``--param aarch64-autovec-preference=<value>`` selector.

    Lets benchmarks force the GCC auto-vectorizer to emit NEON-only or
    SVE-only code on a host that supports both. Useful when one ISA's
    intrinsic dispatch makes a kernel ten times faster than the other
    and you want to attribute the gap.

    Values mirror GCC's documented choices (``man g++``, search
    ``aarch64-autovec-preference``):

    * ``DEFAULT``      -- balanced; the compiler chooses.
    * ``ASIMD_ONLY``   -- NEON-only; SVE never selected.
    * ``SVE_ONLY``     -- SVE-only; NEON never selected.
    * ``PREFER_ASIMD`` -- prefer NEON when both apply.
    * ``PREFER_SVE``   -- prefer SVE when both apply.

    GCC-only knob. For Clang/ICPX the flag is silently skipped (the
    LLVM equivalent uses ``-mattr=+sve`` / ``-mattr=+neon`` and is
    target-feature-driven rather than a single param).
    """
    DEFAULT = "default"
    ASIMD_ONLY = "asimd-only"
    SVE_ONLY = "sve-only"
    PREFER_ASIMD = "prefer-asimd"
    PREFER_SVE = "prefer-sve"


EXECUTABLE_BY_COMPILER: Dict[Compiler, str] = {
    Compiler.CLANG: "clang++",
    Compiler.GCC: "g++",
    Compiler.ICPX: "icpx",
}

#: Flags shared across all (compiler, cost-model) combinations. Pulled
#: from the paper's Table 2 "Default" row + artifact baseline; the
#: ``-march=native`` is omitted here and added at composition time so
#: ARM hosts (``CPU_NAME=arm``) can drop it cleanly.
BASELINE_FLAGS: Tuple[str, ...] = (
    "-O3",
    "-std=c++17",
    "-fPIC",
    "-ffast-math",
    "-fno-math-errno",
    "-fstrict-aliasing",
    "-fopenmp",
    "-faligned-new",
)

#: Link flags shared across all combinations.
LINK_BASE_FLAGS: Tuple[str, ...] = ("-shared", "-fopenmp")

#: Per-(compiler, cost-model) flag additions (delta on top of
#: ``BASELINE_FLAGS``). ``vector_width`` is a placeholder substituted by
#: :func:`get_flags` with the resolved width.
_DELTAS: Dict[Tuple[Compiler, CostModel], Tuple[str, ...]] = {
    # ---- CLANG --------------------------------------------------------
    # Default = baseline only.
    (Compiler.CLANG, CostModel.DEFAULT): (),
    # "Cheap" on Clang has no user-facing cost-model knob; the
    # paper/artifacts treat ``-mprefer-vector-width=512`` as the
    # next-step-down from default. Resolved per CPU at compose time.
    (Compiler.CLANG, CostModel.CHEAP): ("-mprefer-vector-width=__VEC_WIDTH__", ),
    # Paper Table 2 "Scalar" row.
    (Compiler.CLANG, CostModel.NO): ("-fno-vectorize", "-fno-slp-vectorize"),

    # ---- GCC ----------------------------------------------------------
    (Compiler.GCC, CostModel.DEFAULT): (),
    # Two flavours are both valid; the artifacts use width-preference for
    # parity, so default to that. The true cheap knob is enabled via
    # ``EXTRA_FLAGS=-fvect-cost-model=cheap -fsimd-cost-model=cheap``.
    (Compiler.GCC, CostModel.CHEAP): ("-mprefer-vector-width=__VEC_WIDTH__", ),
    # Paper note: GCC scalar variant.
    (Compiler.GCC, CostModel.NO): ("-fno-tree-vectorize", "-fno-tree-slp-vectorize"),

    # ---- ICPX ---------------------------------------------------------
    (Compiler.ICPX, CostModel.DEFAULT): (),
    # Paper note: on Intel, width-preference becomes
    # -qopt-zmm-usage=high (512) or -qopt-ymm-usage=high (256).
    (Compiler.ICPX, CostModel.CHEAP): ("__ICPX_WIDTH_FLAG__", ),
    # Artifact form (preferred over -fno-vectorize spelling).
    (Compiler.ICPX, CostModel.NO): ("-no-vec", ),
}

#: Math-call vectorization additions per compiler. ``-fno-math-errno`` is
#: already in :data:`BASELINE_FLAGS`; these add the vector libm
#: connection. Empty tuple means "no extra flag needed; the baseline
#: already covers it" (gcc-on-glibc, icpx-svml).
_MATH_FLAGS: Dict[Compiler, Tuple[str, ...]] = {
    Compiler.CLANG: ("-fveclib=libmvec", ),
    Compiler.GCC: (),  # libmvec implicit via baseline on Linux/glibc.
    Compiler.ICPX: (),  # SVML linked automatically with -O3 -ffast-math.
}

#: Known-SKU fallback table -- only used when both ``VEC_WIDTH`` and
#: live ``lscpu`` / ``/proc/cpuinfo`` probing fail (e.g. cross-compiling
#: for a CPU we are not running on). Add entries here when a SKU's
#: shipping vector width can't be auto-detected.
_CPU_VEC_WIDTH_FALLBACK: Dict[str, int] = {
    "intel_xeon": 512,  # AVX-512
    "amd_epyc": 256,  # Milan = AVX2-only
    "amd_epyc_genoa": 512,  # Zen 4 = AVX-512
    "arm": 128,  # generic placeholder; NEON baseline
    "arm_grace": 128,  # Grace = Neoverse V2 NEON
    "ibm_power": 128,  # AltiVec / VSX
    "fugaku_a64fx": 512,  # SVE 512-bit
}

#: SVE vector length probed from /proc/cpuinfo or sysconf. Lazily
#: populated on first read; -1 means "not yet probed".
_SVE_BITS_CACHE: Dict[str, int] = {"value": -1}

#: ICPX wide-width sub-flag, picked per resolved vector width.
_ICPX_WIDTH_FLAG_FOR_WIDTH: Dict[int, str] = {
    512: "-qopt-zmm-usage=high",
    256: "-qopt-ymm-usage=high",
    128: "-qopt-ymm-usage=high",  # icpx exposes only zmm/ymm switches; ymm covers 128/256.
}


def _read_cpuinfo_flags() -> List[str]:
    """Return the union of x86 / aarch64 feature-flag tokens from
    ``/proc/cpuinfo``. Empty list if the file is missing or unreadable
    (non-Linux hosts)."""
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
    """Probe SVE vector length in bits via ``getauxval(AT_HWCAP)`` +
    ``prctl(PR_SVE_GET_VL)``. Returns ``0`` if not available."""
    if _SVE_BITS_CACHE["value"] != -1:
        return _SVE_BITS_CACHE["value"]
    bits = 0
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        PR_SVE_GET_VL = 51  # asm-generic/prctl.h
        # prctl returns the SVE vector length in bytes (low 16 bits).
        ret = libc.prctl(PR_SVE_GET_VL, 0, 0, 0, 0)
        if ret > 0:
            bits = (ret & 0xFFFF) * 8
    except Exception:
        bits = 0
    _SVE_BITS_CACHE["value"] = bits
    return bits


def detect_local_vector_width(default: int = 256) -> int:
    """Detect the host CPU's preferred vector width in bits.

    Probe order:

    1. ``VEC_WIDTH`` env var (caller override; trusted).
    2. SVE: read SVE vector length via ``prctl(PR_SVE_GET_VL)`` when the
       ``sve`` feature is reported. SVE width is variable (128..2048 in
       128-bit steps) and is what the running silicon actually has.
    3. x86 ``/proc/cpuinfo`` flags: ``avx512f`` -> 512, ``avx2`` /
       ``avx`` -> 256, ``sse2`` and below -> 128.
    4. aarch64 ``Features`` line: ``asimd`` (NEON) -> 128.
    5. ``default`` (256, matching the artifacts' AVX2 fallback).
    """
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
    """Resolve the preferred vector width (bits) for ``cpu``.

    Resolution order:

    1. ``VEC_WIDTH`` env var (caller override).
    2. ``cpu`` is ``None`` / ``"local"`` -> live host probe via
       :func:`detect_local_vector_width`.
    3. ``cpu`` is a known SKU in :data:`_CPU_VEC_WIDTH_FALLBACK`.
    4. ``default``.
    """
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
    compiler: Compiler
    cost_model: CostModel
    math: bool
    compile_flags: Tuple[str, ...]
    link_flags: Tuple[str, ...]
    cpu: Optional[str] = None
    arm_autovec: Optional[ArmAutovecPreference] = None
    rationale: str = ""

    def compile_flag_str(self) -> str:
        return " ".join(self.compile_flags)

    def link_flag_str(self) -> str:
        return " ".join(self.link_flags)


def _resolve_placeholders(flags: Iterable[str], cpu: Optional[str]) -> List[str]:
    """Replace ``__VEC_WIDTH__`` / ``__ICPX_WIDTH_FLAG__`` placeholders.

    Width is resolved via :func:`vector_width_for_cpu`. Unknown
    placeholders are passed through untouched (the build will fail noisily
    rather than silently miscompile).
    """
    width = vector_width_for_cpu(cpu)
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


#: Set of ``cpu`` values that resolve to an aarch64 target.
_AARCH64_CPUS = frozenset(("arm", "arm_grace", "fugaku_a64fx", "apple_m_series"))


def _is_aarch64_cpu(cpu: Optional[str]) -> bool:
    """Return ``True`` when the resolved CPU is an aarch64 target.

    ``None`` means "the local host" and is treated as aarch64 only if
    the host actually reports ``asimd`` / ``neon`` / ``sve`` in its
    feature flags. This keeps the ARM-specific knob a no-op on x86
    hosts without forcing every caller to thread CPU strings through.
    """
    if cpu is None:
        flags = _read_cpuinfo_flags()
        return any(f in flags for f in ("asimd", "neon", "sve"))
    return cpu in _AARCH64_CPUS


def _rationale_for(compiler: Compiler,
                   cost_model: CostModel,
                   math: bool,
                   arm_autovec: Optional[ArmAutovecPreference] = None) -> str:
    base = {
        (Compiler.CLANG, CostModel.DEFAULT): "Clang -O3 baseline; paper Table 2 Default row + artifact additions.",
        (Compiler.CLANG, CostModel.CHEAP):
        "Clang -mprefer-vector-width=N (no user-facing cheap knob; width hint = paper's next step down).",
        (Compiler.CLANG, CostModel.NO): "Clang -fno-vectorize -fno-slp-vectorize (paper Scalar row).",
        (Compiler.GCC, CostModel.DEFAULT): "GCC -O3 baseline (auto-vectorize implicit at -O3).",
        (Compiler.GCC, CostModel.CHEAP):
        "GCC width hint; for the true cheap knob set EXTRA_FLAGS='-fvect-cost-model=cheap -fsimd-cost-model=cheap'.",
        (Compiler.GCC, CostModel.NO): "GCC -fno-tree-vectorize -fno-tree-slp-vectorize.",
        (Compiler.ICPX, CostModel.DEFAULT): "icpx -O3 baseline (LLVM-based, accepts Clang-style flags).",
        (Compiler.ICPX, CostModel.CHEAP):
        "icpx -qopt-zmm-usage=high / -qopt-ymm-usage=high per the paper note (replaces -mprefer-vector-width=).",
        (Compiler.ICPX, CostModel.NO): "icpx -no-vec (artifact form).",
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
    """Resolve the canonical flag list for the requested combination.

    :param compiler: which compiler to target.
    :param cost_model: which cost-model preset to apply.
    :param math: if ``True``, append the compiler's math-call
                 vectorization flags so sin/cos/log/exp inside loops can
                 lower to the vector libm.
    :param cpu: optional CPU SKU name (e.g. ``intel_xeon``,
                ``amd_epyc``). Drives the wide-width hint and is recorded
                on the returned :class:`FlagSet` for traceability.
    :param include_march_native: include ``-march=native`` in the
                                 resulting flags. Set to ``False`` for
                                 ARM cross-compiles where the paper
                                 omits it.
    :param arm_autovec: optional :class:`ArmAutovecPreference` to force
                        the GCC ARM auto-vectorizer into NEON-only or
                        SVE-only code. Emitted as
                        ``--param=aarch64-autovec-preference=<value>``.
                        Silently dropped when ``compiler`` is not GCC
                        or when the resolved target is not aarch64 (so
                        an x86 benchmark with the flag set still
                        compiles).
    :param extra: optional caller-supplied extra flags appended at the
                  end (e.g. ``-fvect-cost-model=cheap`` for GCC's true
                  cheap knob, or ``-vec-threshold0`` for icpx).
    :returns: a frozen :class:`FlagSet` carrying compile + link flag
              tuples and a short rationale string.
    """
    flags: List[str] = list(BASELINE_FLAGS)
    if include_march_native and (cpu != "arm"):
        flags.append("-march=native")
    flags.extend(_DELTAS[(compiler, cost_model)])
    flags = _resolve_placeholders(flags, cpu)
    if math:
        flags.extend(_MATH_FLAGS[compiler])
    if arm_autovec is not None and compiler is Compiler.GCC and _is_aarch64_cpu(cpu):
        flags.append(f"--param=aarch64-autovec-preference={arm_autovec.value}")
    flags.extend(extra)
    return FlagSet(compiler=compiler,
                   cost_model=cost_model,
                   math=math,
                   compile_flags=tuple(flags),
                   link_flags=tuple(LINK_BASE_FLAGS),
                   cpu=cpu,
                   arm_autovec=arm_autovec,
                   rationale=_rationale_for(compiler, cost_model, math, arm_autovec))


def iter_combinations(cpu: Optional[str] = None, math: bool = False) -> Iterable[FlagSet]:
    """Yield a :class:`FlagSet` for every (compiler, cost-model) combo on
    one CPU. Useful for sweep drivers and the populate scripts."""
    for compiler in Compiler:
        for cm in CostModel:
            yield get_flags(compiler, cm, math=math, cpu=cpu)
