#!/bin/bash
# GCC counterpart to scripts_clang.sh. Manually reproduces, for one
# hand-edited kernel, what only_vec.py's compile_cell() does for
# --compilers gcc --cost-models unlimited --cpus arm_grace on daint
# (see daint_batch_only_vec_gcc.sh), using the canonical GCC/unlimited/
# arm_grace flags from get_flags() + get_remark_flags().
#
# PASTE THIS INTO THE TERMINAL, don't `bash scripts.sh` it. No set -e/-u
# on purpose: this file is meant to be copy-pasted line-by-line or in
# blocks into an already-running shell, and -e/-u there means one typo
# or unset-var reference silently kills your current shell -- which,
# since uenv/venv are layered on top of it, drops you back to a bare
# shell with no uenv view and no venv, and every following command
# quietly runs against system g++ 7.5.0 instead. If that happens, the
# tell is the "(daint_venv)" prompt prefix disappearing -- redo the
# `uenv start` + `source .../activate` lines below and carry on.

uenv start prgenv-gnu/26.3:v1 --view=default
source ~/VectraArtifacts/daint_venv/bin/activate

# Resolve g++ explicitly rather than trusting an ambient $CXX, and check
# the version: skip --view=default above and this silently falls back to
# the ancient system g++ (SUSE stock 7.5.0), which doesn't know
# -std=gnu++20 and fails deep inside vec_remarks_manual.rpt instead of
# loudly at the prompt.
CXX="$(command -v g++)"
echo "Using CXX=$CXX ($($CXX --version | head -1))"
gcc_major="$($CXX -dumpversion | cut -d. -f1)"
[[ "$gcc_major" -lt 10 ]] && echo "WARNING: $CXX is GCC $($CXX -dumpversion) (<10, no -std=gnu++20) -- uenv view not active, run 'uenv view default'" >&2

KDIR="/capstor/scratch/cscs/abonsall/results_dace/tsvc_2/double/gcc_arm_grace_unlimited/build/s314_d_single/build/s314_d_single_s314_d_single"
SRC="$KDIR/src/cpu/s314_d_single_s314_d_single_manual.cpp"   # your edited copy
DACE_INC="$(python3 -c 'import dace, os; print(os.path.dirname(dace.__file__))')/runtime/include"

$CXX \
  -DDACE_BINARY_DIR=\"$KDIR/build\" -Ds314_d_single_s314_d_single_EXPORTS \
  -I"$DACE_INC" \
  -O3 -std=gnu++20 -fPIC \
  -funsafe-math-optimizations -fno-math-errno -ffinite-math-only -fno-signaling-nans -fstrict-aliasing -faligned-new \
  -fopenmp -march=native \
  -ftree-vectorize -fvect-cost-model=unlimited \
  -fopt-info-all \
  -S -o vec_check_manual.s "$SRC" 2> vec_remarks_manual.rpt
  # ^ swap -fno-math-errno for -funsafe-math-optimizations above to test
  #   the unsafe-math variant (allows algebra reordering + reciprocal
  #   approximations) instead of re-pasting the whole block.

cat vec_remarks_manual.rpt

# ---------------------------------------------------------------------------
# Induction-variable-optimization report (separate from the -fopt-info-all
# block above: ivopts isn't one of the -fopt-info categories -- vec, loop,
# inline, omp, ipa, all -- so it never showed up in vec_remarks_manual.rpt).
# This re-runs the same compile with the ivopts tree dump enabled instead,
# writing a *separate* file rather than stderr, so it's picked up via find
# afterwards instead of a redirect.

$CXX \
  -DDACE_BINARY_DIR=\"$KDIR/build\" -Ds314_d_single_s314_d_single_EXPORTS \
  -I"$DACE_INC" \
  -O3 -std=gnu++20 -fPIC \
  -funsafe-math-optimizations -fno-math-errno -ffinite-math-only -fno-signaling-nans -fstrict-aliasing -faligned-new \
  -fopenmp -march=native \
  -ftree-vectorize -fvect-cost-model=unlimited \
  -fdump-tree-ivopts-details \
  -S -o vec_check_manual_ivopts.s "$SRC"

IVOPTS_DUMP="$(find . -maxdepth 1 -name '*.ivopts' -newer vec_check_manual_ivopts.s -print -quit)"
[[ -z "$IVOPTS_DUMP" ]] && IVOPTS_DUMP="$(find . -maxdepth 1 -name '*.ivopts' -print -quit)"
echo "ivopts dump: $IVOPTS_DUMP"
cat "$IVOPTS_DUMP"
