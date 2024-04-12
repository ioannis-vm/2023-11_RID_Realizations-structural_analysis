#!/bin/bash
#SBATCH -J %jobname%
#SBATCH -o extra/structural_analysis/tacc/%jobname%_log_%j
#SBATCH -N %num_nodes%                  # number of nodes requested
#SBATCH -n %num_tasks%                  # total number of tasks to run in parallel
#SBATCH -p %partition%                  # queue (partition)
#SBATCH -t %time%                       # run time (hh:mm:ss)
#SBATCH -A DesignSafe-HPC4PBEE          # Allocation name to charge job against

source $(HOME)/env_setup.sh
export PYTHONPATH=$PYTHONPATH:$(pwd)
export LAUNCHER_WORKDIR=/scratch1/07506/usr83847/2023-11_RID_Realizations/
export OMP_NUM_THREADS=1
export LAUNCHER_JOB_FILE=extra/structural_analysis/tacc/%jobname%_taskfile
${LAUNCHER_DIR}/paramrun
