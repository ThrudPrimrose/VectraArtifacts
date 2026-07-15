#!/bin/bash
# check_gcc_versions.sh
# Loops through all prgenv-gnu(-*) uenv images already in your local repo
# (from `uenv image ls`), starts each one, and prints its gcc version.
set -x

UENVS=(
        "cp2k/2024.1:v1"
"cp2k/2024.2:v1"
"cp2k/2024.3:v1"
"cp2k/2025.1:v2"
"cp2k/2025.1:v3"
"cp2k/2026.1:v1"
"editors/24.7:rc1"
"editors/24.7:v2"
"esmf/26.2:v1"
"gromacs/2024:v1"
"gromacs/2025.0:v1"
"julia/24.9:v1"
"julia/25.5:v1"
"jupyterlab/v4.1.8:v1"
"jupyterlab/v4.1.8:v2"
"jupyterlab/v4.1.8:v3"
"lammps/2024:v1"
"lammps/20251210:v1"
"lammps/20251210:v2"
"linalg/24.11:rc1"
"linalg/24.11:v1"
"linalg/24.11:v2"
"linalg/25.10:v1"
"linalg-complex/24.11:v1"
"linalg-complex/24.11:v2"
"linalg-complex/25.10:v1"
"linaro-forge/25.1:v2"
"linaro-forge/26.0:v1"
"namd/3.0:v1"
"netcdf-tools/2025:v1"
"netcdf-tools/2025:v2"
"paraview/5.13.2:v2"
"paraview/6.0.1:v2"
"paraview/6.1:v1"
"prgenv-gnu/24.11:v1"
"prgenv-gnu/24.11:v2"
"prgenv-gnu/24.7:v1"
"prgenv-gnu/25.11:v1"
"prgenv-gnu/25.6:v1"
"prgenv-gnu/25.6:v2"
"prgenv-gnu/26.3:v1"
"prgenv-gnu-openmpi/25.12:v1"
"prgenv-gnu-openmpi/26.3:v1"
"prgenv-intel/2022.1:v1"
"q-e-sirius/v1.0.1:v2"
"q-e-sirius/v1.0.2:v1"
"quantumespresso/v7.3.1:v1"
"quantumespresso/v7.3.1:v2"
"quantumespresso/v7.4.1:v1"
"quantumespresso/v7.4.1:v2"
"quantumespresso/v7.5:v1"
"quantumespresso/v7.5:v2"
"vasp/v6.5.0:v1"
"vasp/v6.6.0:v1"
)

for u in "${UENVS[@]}"; do
  version=$(uenv image pull "$u")

done