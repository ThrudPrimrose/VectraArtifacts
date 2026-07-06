# VectraArtifacts

Auto-vectorization benchmark grid for the TSVC-2 loop suite, plus a
`tsvc_2_5` extension corpus that targets symbolic-step / symbolic-offset
/ quasi-affine patterns. Stores per-kernel parallelization audit + per-run
measurements in a single SQLite DB; renders Markdown and LaTeX tables for
the paper.

Repository: <https://github.com/ThrudPrimrose/VectraArtifacts>

## Install

```bash
pip install -e ".[dev]"   # adds pytest + yapf
```

### DaCe backend (for the `tsvc_2_5` SDFG kernels)

The `tsvc_2_5` kernels depend on the canonicalize + vectorization passes that
live on the **`yakup/dev`** branch of [`spcl/dace`](https://github.com/spcl/dace),
not yet in a tagged PyPI release. DaCe **must** be pinned to `yakup/dev` —
`main` (and the PyPI release) lack these passes and will not work.
**Recommended:** clone DaCe and install it editable from a local path, so your
DaCe edits are picked up immediately and a single `git pull` updates the
backend:

```bash
git clone https://github.com/spcl/dace.git /path/to/dace
git -C /path/to/dace checkout yakup/dev   # REQUIRED: must be on yakup/dev
pip install -e /path/to/dace              # editable DaCe checkout
pip install -e ".[dev]"                   # this repo (no [dace] — keeps your checkout)

# later, to update DaCe (stay on yakup/dev):
git -C /path/to/dace checkout yakup/dev && git -C /path/to/dace pull
```

If you already have a DaCe checkout, switch it to the branch before
installing — any other branch will fail to build the `tsvc_2_5` kernels:

```bash
git -C /path/to/dace checkout yakup/dev
```

Alternatively, let the `[dace]` extra pull the branch directly (no local
checkout, but you can't edit DaCe and pip won't refetch on branch advance):

```bash
pip install -e ".[dace]"
# the extra resolves to (always yakup/dev):
#   dace @ git+https://github.com/spcl/dace.git@yakup/dev
# force a refetch after the branch advances (pip caches the URL requirement):
pip install -e ".[dace]" --force-reinstall --no-deps
```

## Populate the database and render the tables

```bash
# 1. seed: parse the 151-row TSVC-2 audit + the 34-row tsvc_2_5 metadata
#    into ./vectra.db, then drop in a deterministic mock run grid so the
#    plot drivers have something to render before real measurements land.
python scripts/populate_example.py
# -> ingested 151 kernel audit rows into suite=tsvc_2
# -> seeded 34 extension kernels into suite=tsvc_2_5
# -> inserted 11655 mock run rows (7 CPUs x 9 (compiler, cost_model) x 185 kernels)

# 2. render the per-kernel audit table (Markdown):
vectra-plot --db vectra.db --kind audit-md --suite tsvc_2   --out audit_tsvc_2.md
vectra-plot --db vectra.db --kind audit-md --suite tsvc_2_5 --out audit_tsvc_2_5.md

# 3. render the perf grid (rows = CPU, columns = compiler x cost-model):
vectra-plot --db vectra.db --kind grid-md  --out grid.md
vectra-plot --db vectra.db --kind grid-tex --out grid.tex     # double-column table*
```

To repopulate from real measurement runs instead of the mock grid, use
the same `populate_example.py` as a template: the only thing that needs
to change is the `mock_runs` block; the seeding + schema are reusable.

## Pin a compiler config per shell

```bash
vectra-source-sh --compiler clang --cost-model cheap --cpu intel_xeon \
                 --math --out scripts/source.clang_cheap.sh
source scripts/source.clang_cheap.sh
python -m tsvc_2.compile_cpp_kernels tsvc_2/tsvc_cpp_microkernels
```

The shim `compiler_config.py` reads the env-var trio
(`CXX_COMPILER` / `CXX_COSTMODEL` / `CXX_MATH` / `CPU_NAME`) into `CXX`,
`COMPILE_FLAGS`, `LINK_FLAGS`. DaCe SDFG compilation picks up the same
flag set via `vectra_artifacts.compilers.configure_dace(...)`.

## Layout

```
src/vectra_artifacts/
    compilers/          (compiler, cost-model, math) -> flags
    database/           SQLite schema + populate + queries
    plotting/           markdown + latex table emitters
    tsvc_audit/         parser for docs/PARALLELIZATION_AUDIT.md
    cli.py              vectra-populate / vectra-plot / vectra-source-sh
docs/
    PARALLELIZATION_AUDIT.md   151-row TSVC-2 audit (parallel-in-principle + DaCe status)
    VECTORIZATION_FLAGS.md     per-(compiler, cost-model, math) flag reference
    COMPILER_VECTORIZER_SURVEY.md   2024-2026 LLVM + GCC autovec capabilities and gaps
tsvc_2/                 151-kernel TSVC-2 corpus (Python + C++ + split/compile/ctypes)
tsvc_2_5/               34-kernel extension corpus (symbolic-step / quasi-affine)
scripts/                populate_example.py + plot_example.py
tests/                  pytest suite (106 tests)
```

## Compiler-flag matrix

3 compilers (`clang` / `gcc` / `icpx`) x 4 cost models
(`default` / `cheap` / `unlimited` / `disabled`) x 2 math-flag values = 24 canonical
combinations, documented in [`docs/VECTORIZATION_FLAGS.md`](docs/VECTORIZATION_FLAGS.md)
and canonicalised in
[`src/vectra_artifacts/compilers/flags.py`](src/vectra_artifacts/compilers/flags.py).

```python
from vectra_artifacts.compilers import Compiler, CostModel, get_flags

fs = get_flags(Compiler.CLANG, CostModel.CHEAP, math=True, cpu="intel_xeon")
print(fs.compile_flag_str())
# -> -O3 -std=c++17 -fPIC -ffast-math ... -mprefer-vector-width=512 -fveclib=libmvec
```

Vector width auto-probes from `/proc/cpuinfo` flags + SVE `prctl(PR_SVE_GET_VL)`
when targeting the local host; known SKUs (`intel_xeon`, `amd_epyc`,
`arm_grace`, ...) have a fallback table; `VEC_WIDTH` overrides both.

On GCC + aarch64 you can additionally force the auto-vectorizer to
NEON-only or SVE-only via `ArmAutovecPreference`:

```python
from vectra_artifacts.compilers import ArmAutovecPreference
fs = get_flags(Compiler.GCC, CostModel.DEFAULT, cpu="arm_grace",
               arm_autovec=ArmAutovecPreference.SVE_ONLY)
# emits --param=aarch64-autovec-preference=sve-only
```

## Corpora

| Corpus | Kernels | Notes |
|---|---|---|
| [`tsvc_2/`](tsvc_2/) | 151 | TSVC-2 reference (Levine/Callahan/Maslov). Per-kernel parallelization status in [`docs/PARALLELIZATION_AUDIT.md`](docs/PARALLELIZATION_AUDIT.md). |
| [`tsvc_2_5/`](tsvc_2_5/) | 34 | Extension corpus: symbolic-step + symbolic-offset + quasi-affine subscripts, fission families, already-tiled stencils (const + symbolic tile size), ECRAD-style clamped reduction, masked stores. |

Both corpora ship a split + compile + ctypes bindings pipeline:

```bash
# build the tsvc_2_5 .so and call a kernel
python -c "from tsvc_2_5 import ExtensionLibrary; lib = ExtensionLibrary()"
```

## Command Flow for vectorisation report

activate venv
specifically for me: conda activate thesis
deactivate vevn
conda deactivate

```bash
vectra-source-sh --compiler {clang, gcc, icpx} --cost-model {default, cheap, unlimited, disabled} --cpu apple_m_series \
                 --out scripts/source.{name}.sh

                 # cpu options: {amd_epyc, amd_epyc_genoa, apple_m_series, arm_grace, fugaku_a64fx, ibm_power, intel_xeon}

source scripts/source.{name}.sh

python3 -m tsvc_2.compile_cpp_kernels tsvc_2/tsvc_cpp_microkernels --vec-report --force -j6
python3 -m tsvc_2.compile_dace_kernels tsvc_2/tsvc_dace_microkernels --vec-report --force -j6
```

## License

TSVC-2 originates from [UoB-HPC/TSVC_2](https://github.com/UoB-HPC/TSVC_2).
