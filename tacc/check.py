"""
Parse SLRUM output files of jobs using `pylaunchermpi` and print
analysis stats.
"""

import re
from glob import glob


def process_output_file(file_path):
    """
    Parses an output file to extract information.

    Parameters
    ----------
    file_path: str
        Path to the output file

    Returns
    -------
    tuple
        - job id
        - number of tasks
        - number of processes (inferred)
        - list of running SHAs
        - list of complete SHAs (without error)
        - list of SHAs that completed with error
        - dict mapping SHA to error message

    """

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    running = []
    complete = []
    error = []
    error_msg = {}

    for line in lines:
        if 'The size is ' in line:
            matched = re.search(r'The size is (\d+)\.', line)
            assert matched
            num_processes = int(matched.group(1))
        if 'Process 0: Parsed ' in line:
            matched = re.search(r'Parsed (\d+) tasks', line)
            assert matched
            ntasks = int(matched.group(1))
        if 'Executing task' in line:
            matched = re.search(r'Executing task (\d+)\.', line)
            assert matched
            task = matched.group(1)
            running.append(task)
        if 'finished successfully' in line:
            matched = re.search(r'Task (\d+) finished successfully.', line)
            if matched:
                task = matched.group(1)
                running.remove(task)
                complete.append(task)
        if 'There was an error with ' in line:
            matched = re.search(r'There was an error with task (\d+)\. stderr:', line)
            if matched:
                task = matched.group(1)
                matched = re.search(r"stderr: `b('.+')`. stdout:", line)
                stderr = matched.group(1)
                error.append(task)
                error_msg[task] = stderr
                running.remove(task)
        if 'TACC:  Starting up job ' in line:
            matched = re.search(r'Starting up job (\d+) \n', line)
            assert matched
            job_id = int(matched.group(1))

    return job_id, ntasks, num_processes, running, complete, error, error_msg


def main():

    directory = (
        '/scratch/07506/usr83847/2023-11_RID_Realizations/'
        'extra/structural_analysis/tacc/20240507/'
    )

    files = glob(
        directory + '*_log.o*',
    )

    for filepath in files:

        print(filepath)

        job_id, ntasks, num_processes, running, complete, error, error_msg = (
            process_output_file(filepath)
        )

        nrunning = len(running)
        util_prc = float(nrunning) / float(num_processes) * 100.00
        nfin = len(complete) + len(error)
        print(f'  Job ID: {job_id}.')
        print(f'  Total number of tasks: {ntasks}.')
        print(f'  Running: {nrunning}. ({util_prc:.0f}% utilization)')
        if util_prc < 50.00:
            print('WARNING: Consider downscaling job.')
        print(f'  Finished (in total): {nfin/ntasks*100:.0f}% ({nfin}).')
        print(f'  Finished with error: {len(error)}.')
        print()


if __name__ == '__main__':
    main()
