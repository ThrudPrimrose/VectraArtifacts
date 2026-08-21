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
#SBATCH --output=tsvc_subset_timing_%j.out
#SBATCH --error=tsvc_subset_timing_%j.err

set -euo pipefail
export PYTHONUNBUFFERED=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

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
LEN_1D="${LEN_1D:-1024}"
OUT_DIR="${OUT_DIR:-results_specific/${TSVC_VERSION}/${SLURM_JOB_ID:-local}}"

echo "Host: $(hostname)"
echo "CXX : ${CXX:-<resolved automatically>}"
echo "Kernels: $KERNELS"

python3 -u time_specific_kernels.py \
    --kernels $KERNELS \
    --tsvc-version "$TSVC_VERSION" \
    --precision "$PRECISION" \
    --compilers $COMPILERS \
    --cost-models $COST_MODELS \
    --cpus $CPUS \
    --runs "$RUNS" \
    --len-1d "$LEN_1D" \
    --out-dir "$OUT_DIR"

echo "Done. Raw per-rep CSVs under results_cpp/${TSVC_VERSION} and results_dace/${TSVC_VERSION};"
echo "normalized combined CSVs + manifest under $OUT_DIR."
echo "Box/violin plots: python3 timing_violinplot.py --results-cpp results_cpp/${TSVC_VERSION} --results-dace results_dace/${TSVC_VERSION} --kernels $KERNELS --out-dir plots/${TSVC_VERSION}_subset"
