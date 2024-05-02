#!/bin/bash
#SBATCH -J %jobname%
#SBATCH -o extra/structural_analysis/tacc/%jobname%_log.o%j
#SBATCH -e extra/structural_analysis/tacc/%jobname%_log.e%j
#SBATCH -p skx                          # Queue (partition) name
#SBATCH -N %num_nodes%                  # number of nodes requested
#SBATCH -n %num_tasks%                  # total number of tasks to run in parallel
#SBATCH -t %time%                       # run time (hh:mm:ss)
#SBATCH -A DesignSafe-HPC4PBEE          # Allocation name to charge job against
#SBATCH --mail-type=all
#SBATCH --mail-user=ioannis_vm@berkeley.edu

source $HOME/.bashrc
micromamba activate rid_prj

export OMP_NUM_THREADS=1
export PYTHONPATH=$PYTHONPATH:$(pwd)
export LAUNCHER_WORKDIR=/scratch/07506/usr83847/2023-11_RID_Realizations/
export LAUNCHER_JOB_FILE=extra/structural_analysis/tacc/%jobname%_taskfile

ibrun pylaunchermpi
