"""
Parse SLRUM output files of jobs using `pylaunchermpi` and print
analysis stats.
"""

import re
from glob import glob


def main():

    directory = (
        '/scratch/07506/usr83847/2023-11_RID_Realizations/'
        'extra/structural_analysis/tacc/'
    )

    files = glob(
        directory + '*_log.o*',
    )

    for filepath in files:

        print(filepath)

        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        commands = {}
        running = []
        complete = []
        error = []

        for line in lines:
            if 'Process 0: Parsed ' in line:
                matched = re.search(r'Parsed (\d+) tasks', line)
                assert matched
                ntasks = int(matched.group(1))
            if 'Executing command' in line:
                matched = re.search(r'Executing command (\S+):', line)
                assert matched
                sha = matched.group(1)
                matched = re.search(r'`(.+)`', line)
                assert matched
                command = matched.group(1)
                commands[sha] = command
                running.append(sha)
            if 'finished successfully' in line:
                matched = re.search(r'Command (\S+) finished successfully.', line)
                assert matched
                sha = matched.group(1)
                running.remove(sha)
                complete.append(sha)
            if 'There was an error with ' in line:
                matched = re.search(r'There was an error with (\S+)', line)
                assert matched
                sha = matched.group(1)
                error.append(sha)
                running.remove(sha)

        # infer number of processes
        num_processes = 0
        for line in lines:
            matched = re.search(r'Process (\d+):', line)
            if matched:
                value = int(matched.group(1))
                num_processes = max(num_processes, value)
        num_processes += 1

        nrunning = len(running)
        util_prc = float(nrunning) / float(num_processes) * 100.00
        nfin = len(complete) + len(error)
        print(f'  Total number of tasks: {ntasks}.')
        print(f'  Running: {nrunning}. ({util_prc:.0f}% utilization)')
        if util_prc < 50.00:
            print(f'WARNING: Consider downscaling job.')
        print(f'  Finished (in total): {nfin/ntasks*100:.0f}% ({nfin}).')
        print(f'  Finished with error: {len(error)}.')
        print()


if __name__ == '__main__':
    main()
