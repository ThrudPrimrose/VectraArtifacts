#!/usr/bin/env bash
# SLURM template for time_specific_kernels.py — raw CPP-vs-DaCe timing of a
# hand-picked TSVC kernel subset. Fill in the site-specific bits marked TODO
# (module loads / venv / compiler paths) for your cluster, then:
#
#   sbatch cluster/time_specific_kernels.sbatch.sh
#
# Override the kernel list / sweep via env vars at submit time, e.g.:
#   KERNELS="s313 s314 s453 vdotr" COMPILERS="clang gcc" CPUS="arm_grace" \
#       RUNS=500 sbatch cluster/time_specific_kernels.sbatch.sh
#
#SBATCH --job-name=tsvc_subset_timing
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --hint=nomultithread
#SBATCH --time=01:00:00
#SBATCH --partition=normal
#SBATCH --account=g34
#SBATCH --uenv=prgenv-gnu/26.3:v1
#SBATCH --view=default
#SBATCH --output=tsvc_subset_timing_%j.out
#SBATCH --error=tsvc_subset_timing_%j.err

set -euo pipefail
export PYTHONUNBUFFERED=1

# sbatch copies this script into a spool dir (/var/spool/slurmd/...) and
# runs it FROM THERE, so ${BASH_SOURCE[0]} at job runtime points at that
# spool copy, not this file's real location in the checkout -- resolving
# ROOT from it silently breaks the relative `python3 time_specific_kernels.py`
# call below. $SLURM_SUBMIT_DIR (the directory `sbatch` was invoked from) is
# what's actually reliable under SLURM; BASH_SOURCE is only a fallback for
# running this script directly with `bash` outside SLURM.
if [[ -n "${SLURM_SUBMIT_DIR:-}" ]]; then
    ROOT="$SLURM_SUBMIT_DIR"
else
    ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
cd "$ROOT"
export PATH="$SCRATCH/llvm-env/view/bin:$PATH"
export LD_LIBRARY_PATH="/capstor/scratch/cscs/abonsall/spack/opt/spack/linux-neoverse_v2/llvm-21.1.4-uyntqbmcpg6nh5xrgtxkoaorygjfxgsh/lib/aarch64-unknown-linux-gnu:$LD_LIBRARY_PATH"
source ~/VectraArtifacts/daint_venv/bin/activate

# TODO: module loads / spack env / venv activation for your cluster, e.g.:
#   module load PrgEnv-gnu
#   source "$ROOT/.venv/bin/activate"
# TODO: point CXX at the exact toolchain this job should use, if the
# default resolved-from-(compiler,cost-model,cpu) executable isn't right:
#   export CXX=/path/to/clang++

KERNELS="${KERNELS:-s313 s314 s453 vdotr}"
TSVC_VERSION="${TSVC_VERSION:-tsvc_2}"
PRECISION="${PRECISION:-double}"
COMPILERS="${COMPILERS:-clang}"
COST_MODELS="${COST_MODELS:-unlimited}"
CPUS="${CPUS:-arm_grace}"
RUNS="${RUNS:-200}"
LEN_1D="${LEN_1D:-2097152}"

# All job output on $SCRATCH, not the repo checkout under $HOME. --out-dir
# alone only relocates the combined/manifest output -- results_cpp/,
# results_dace/, and the two compile-artifact build dirs are separate
# flags and each needs pointing at $SCRATCH too.
SCRATCH_BASE="$SCRATCH/tsvc_subset_timing"
JOB_TAG="${SLURM_JOB_ID:-local}"
RESULTS_CPP="$SCRATCH_BASE/results_cpp/${TSVC_VERSION}"
RESULTS_DACE="$SCRATCH_BASE/results_dace/${TSVC_VERSION}"
BUILD_DIR="$SCRATCH_BASE/build/${JOB_TAG}"
OUT_DIR="$SCRATCH_BASE/results_specific/${TSVC_VERSION}/${JOB_TAG}"
mkdir -p "$RESULTS_CPP" "$RESULTS_DACE" "$BUILD_DIR" "$OUT_DIR"

echo "Host: $(hostname)"
echo "CXX : ${CXX:-<resolved automatically>}"
echo "Kernels: $KERNELS"
echo "Output on scratch: $SCRATCH_BASE"

python3 -u time_specific_kernels.py \
    --kernels $KERNELS \
    --tsvc-version "$TSVC_VERSION" \
    --precision "$PRECISION" \
    --compilers $COMPILERS \
    --cost-models $COST_MODELS \
    --cpus $CPUS \
    --runs "$RUNS" \
    --len-1d "$LEN_1D" \
    --results-cpp "$RESULTS_CPP" \
    --results-dace "$RESULTS_DACE" \
    --build-dir "$BUILD_DIR" \
    --out-dir "$OUT_DIR"

echo "Done. Raw per-rep CSVs under $RESULTS_CPP and $RESULTS_DACE;"
echo "normalized combined CSVs + manifest under $OUT_DIR."
echo "Box/violin plots: python3 timing_violinplot.py --results-cpp $RESULTS_CPP --results-dace $RESULTS_DACE --kernels $KERNELS --out-dir $SCRATCH_BASE/plots/${TSVC_VERSION}_subset"
