#!/bin/bash
# Clang counterpart to scripts.sh. Manually reproduces, for one hand-edited
# kernel, what only_vec.py's compile_cell() does for --compilers clang
# --cost-models unlimited --cpus arm_grace on daint, using the same
# uenv/PATH/LD_LIBRARY_PATH pinning as the real clang sweep (see
# cluster/daint_fulltime_cloudsc_clang.sh / daint_batch_only_vec_clang.sh)
# and the canonical clang/unlimited/arm_grace flags from
# scripts/source.clang_arm_grace_unlimited.sh. Pinning clang++ explicitly
# matters here: an ambient $CXX on daint resolves to GCC by default, which
# silently produces a GCC-format -fopt-info report for a directory labelled
# clang_arm_grace_unlimited.
#
# PASTE THIS INTO THE TERMINAL, don't `bash scripts_clang.sh` it. No
# set -e/-u on purpose: this file is meant to be copy-pasted line-by-line
# or in blocks into an already-running shell, and -e/-u there means one
# typo or unset-var reference silently kills your current shell -- which,
# since uenv/llvm-env/venv are layered on top of it, drops you back to a
# bare shell with none of them active. If the "(daint_venv)" prompt prefix
# disappears, redo the lines below from the top.

uenv start prgenv-gnu/26.3:v1 --view=default

# Same LLVM build the real clang sweep runs against (see the sbatch job's
# PATH/LD_LIBRARY_PATH exports). Prefer the spack-env view symlink; fall
# back to the spack package path directly if the view isn't there.
if [[ -x "$SCRATCH/llvm-env/view/bin/clang++" ]]; then
  export PATH="$SCRATCH/llvm-env/view/bin:$PATH"
else
  export PATH="/capstor/scratch/cscs/abonsall/spack/opt/spack/linux-neoverse_v2/llvm-21.1.4-uyntqbmcpg6nh5xrgtxkoaorygjfxgsh/bin:$PATH"
fi
export LD_LIBRARY_PATH="/capstor/scratch/cscs/abonsall/spack/opt/spack/linux-neoverse_v2/llvm-21.1.4-uyntqbmcpg6nh5xrgtxkoaorygjfxgsh/lib/aarch64-unknown-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
source ~/VectraArtifacts/daint_venv/bin/activate

CXX="$(command -v clang++)"
echo "Using CXX=$CXX ($($CXX --version | head -1))"
[[ "$CXX" != "$SCRATCH"/llvm-env/* && "$CXX" != /capstor/scratch/cscs/abonsall/spack/* ]] && echo "WARNING: $CXX isn't the pinned LLVM build -- PATH prepend above didn't take" >&2

KDIR="/capstor/scratch/cscs/abonsall/results_dace/tsvc_2/double/clang_arm_grace_unlimited/build/s453_d_single/build/s453_d_single_s453_d_single"
SRC="$KDIR/src/cpu/s453_d_single_s453_d_single_manual.cpp"   # your edited copy
DACE_INC="$(python3 -c 'import dace, os; print(os.path.dirname(dace.__file__))')/runtime/include"

$CXX \
  -DDACE_BINARY_DIR=\"$KDIR/build\" -Ds453_d_single_s453_d_single_EXPORTS \
  -I"$DACE_INC" \
  -O3 -std=gnu++20 -fPIC \
  -fno-math-errno -ffinite-math-only -fno-signaling-nans -fstrict-aliasing -faligned-new \
  -fopenmp -march=native \
  -fvectorize -fslp-vectorize -mllvm -force-vector-width=4 \
  -Rpass=loop-vectorize -Rpass-missed=loop-vectorize -Rpass-analysis=loop-vectorize \
  -Rpass=slp-vectorize -Rpass-missed=slp-vectorize -Rpass-analysis=slp-vectorize \
  -S -o vec_check_manual_clang.s "$SRC" 2> vec_remarks_manual_clang.rpt
  # ^ add -funsafe-math-optimizations above to test the unsafe-math variant
  #   (allows algebra reordering + reciprocal approximations), same as the
  #   GCC script's toggle.

cat vec_remarks_manual_clang.rpt
