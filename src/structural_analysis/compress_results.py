from mpi4py import MPI
from datetime import datetime
from time import perf_counter
from time import sleep
import numpy as np
from extra.structural_analysis.src.db import DB_Handler


def message(text):
    """
    Prints a message to stdout including the process ID and a
    timestamp.

    """
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    current_time = datetime.now()
    time_string = current_time.strftime("%H:%M:%S")
    message = f'{time_string} | Process {rank}: ' + text
    print(message, flush=True)


def main():

    result_number = '3'

    t_start = perf_counter()

    # Initialize the MPI environment
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    size = comm.Get_size()

    # The master process (rank 0) will read the commands and distribute them
    if rank == 0:

        # read avaiable identifiers
        db_handler = DB_Handler(
            db_path=f'extra/structural_analysis/results/results_{result_number}.sqlite'
        )
        identifiers = db_handler.list_identifiers()

        message(f'Found {len(identifiers)} identifiers.')

    else:
        commands = None  # noqa: F841

    # Scatter commands to all processes, assuming the number of commands
    # is at least the number of processes
    if rank == 0:
        # Allocate identifiers to processes
        allocated_identifiers = [[] for _ in range(size)]
        for i, identifier in enumerate(identifiers):
            allocated_identifiers[i % size].append(identifier)
    else:
        allocated_identifiers = None

    # Distribute the identifiers
    identifiers_for_process = comm.scatter(allocated_identifiers, root=0)

    # Wait a bit for other processes to perform their IO operations
    sleep(rank)  # i.e., process 1 will start after 1 sec

    db_handler = DB_Handler(
        db_path=f'extra/structural_analysis/results/results_{result_number}.sqlite'
    )
    db_handler_res = DB_Handler(
        db_path=(
            f'extra/structural_analysis/results/compressed/'
            f'results_{result_number}_compressed_{rank}.sqlite'
        )
    )
    existing_results = set(db_handler_res.list_identifiers())

    # Each process runs its allocated identifiers
    for i, identifier in enumerate(identifiers_for_process):
        if identifier in existing_results:
            message(f"Skipping as it already exists: `{identifier}`")
            continue
        message(
            f"Executing identifier {i+1}/{len(identifiers_for_process)}: `{identifier}`"
        )
        df, metadata, log_content = db_handler.retrieve_data(identifier)
        # need some robust approach here
        df = df.set_index('time')
        step = 0.01
        new_index = np.arange(df.index.min(), df.index.max() + step, step)
        df_resampled = df.reindex(new_index).interpolate(method='index')
        df_resampled['Subdiv'] = df_resampled['Subdiv'].astype('int')
        db_handler_res.store_data(identifier, df_resampled, metadata, log_content)

    t_end = perf_counter()

    message(f'Done with all tasks. ' f'Elapsed time: {t_end - t_start:.2f} s.')


if __name__ == '__main__':
    main()
