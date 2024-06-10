"""
Parse SLRUM output files of jobs using `pylaunchermpi` and print
analysis stats.
"""

import re
import subprocess
from glob import glob


# pylint: disable=subprocess-run-check


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
            matched = re.search(
                r'There was an error with task (\d+)\. stderr:', line
            )
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
        'extra/structural_analysis/tacc/'
    )

    files = glob(
        directory + '*_log.o*',
    )

    # files = [
    #     f'{directory}/20240520_nlth_group_8001_2_log.o545949',
    # ]

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
        print(f'  Finished (in total): {nfin / ntasks * 100:.0f}% ({nfin}).')
        print(f'  Finished with error: {len(error)}.')
        print()


if __name__ == '__main__':
    main()


def get_remaining_tasks(output_file):
    """
    Create SLRUM files for cancelled jobs that had running tasks, used
    when downscaling a job that is almost finished but has a few long
    tasks and we want to avoid being charged for the inactive nodes.

    """

    job_id, ntasks, num_processes, running, complete, error, error_msg = (
        process_output_file(output_file)
    )

    with open(output_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # get a dict mapping task IDs to their command
    for line in lines:
        if 'Process 0: Parsed ' in line:
            matched = re.search(r'Tasks: {(.+)}$', line)
            assert matched
            tasks = matched.group(1)
    tasks_dict = {}
    tasks_list = tasks.split(',')
    for thing in tasks_list:
        tid, tstr = thing.split(':')
        tasks_dict[tid.strip()] = tstr.replace('"', '').strip()

    # get a list with the commands that were still running
    remaining_tasks = []
    for thing in running:
        remaining_tasks.append(tasks_dict[thing] + '\n')

    return remaining_tasks

    # # put them in a file
    # with open(taskfile_path, 'w', encoding='utf-8') as f:
    #     f.writelines(remaining_tasks)

    # print(f'Remaining tasks: {len(remaining_tasks)}')


def get_all_remaining_tasks():
    """
    Get all remaining tasks.
    """

    res = subprocess.run(
        ['squeue', '--me'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    running_job_ids = set(
        [x.strip().split(' ')[0] for x in res.stdout.split('\n')][1:][:-1]
    )

    output_files = glob('*.o*')
    stopped = []
    for output_file in output_files:
        job_id = output_file.split('.o')[1]
        if job_id not in running_job_ids:
            stopped.append(output_file)

    remaining_tasks = []
    for stopped_file in stopped:
        remaining_tasks.extend(get_remaining_tasks(stopped_file))

    print('Number of nodes to finish in one go:')
    print(int(len(remaining_tasks) / 47 + 1))

    # put them in a file
    with open('remaining_taskfile', 'w', encoding='utf-8') as f:
        f.writelines(remaining_tasks)
