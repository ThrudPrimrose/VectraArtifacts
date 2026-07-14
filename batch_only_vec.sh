#!/bin/bash
#SBATCH --job-name=vectorisation-of-tsvc_2
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=72
#SBATCH --hint=nomultithread
#SBATCH --time=04:00:00
#SBATCH --partition=normal
#SBATCH --account=g34
#SBATCH --output=perf_%j.out
#SBATCH --error=perf_%j.err

srun python only_vec.py --compilers gcc --cost-models default cheap unlimited disabled --precision both --tsvc-version tsvc_2 --cpus arm_grace -j ${SLURM_CPUS_PER_TASK}