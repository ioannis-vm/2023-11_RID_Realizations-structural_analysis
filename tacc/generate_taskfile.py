"""
Generate a taskfile to run the analysese on TACC
"""

from itertools import product
import sys
import logging
import re
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor
from tqdm import tqdm
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from osmg.ground_motion_utils import import_PEER
from extra.structural_analysis.src.util import read_study_param
from extra.structural_analysis.src.db import DB_Handler
from extra.structural_analysis.src.util import retrieve_peer_gm_data

logging.basicConfig(
    level=logging.INFO,  # Set the logging level (e.g., INFO, DEBUG, WARNING)
    format='%(asctime)s - %(levelname)s - %(message)s',  # Include timestamp
    stream=sys.stdout,  # Write logs to stdout
    datefmt='%Y-%m-%d %H:%M:%S',  # Set the timestamp format
)


def main():
    log = logging.getLogger(__name__)

    #
    # set parameters
    #

    date_prefix = '20240502'

    #
    # retrieve study variables
    #

    nhz = int(read_study_param('extra/structural_analysis/data/study_vars/m'))
    ngm_cs = int(read_study_param('extra/structural_analysis/data/study_vars/ngm_cs'))
    ngm_cms = int(read_study_param('extra/structural_analysis/data/study_vars/ngm_cms'))
    ngm_pulse = int(
        float(read_study_param('extra/structural_analysis/data/study_vars/ngm_cms'))
        / 4.00
    )

    #
    # generate cases
    #

    log.info('Generate cases')
    hazard_levels = [f'{i+1}' for i in range(nhz)]
    ground_motions = [f'{i+1}' for i in range(ngm_cs)]
    ground_motions_cms = [f'{i+1}' for i in range(ngm_cms)]
    ground_motions_pulse = [f'{i+1}' for i in range(ngm_pulse)]
    directions = ('x', 'y')
    codes = ("smrf", "scbf", "brbf")
    stories = ("3", "6", "9")
    rcs = ("ii", "iv")
    suites = ('cms', 'cs')
    cases = [f"{c}_{s}_{r}" for c in codes for s in stories for r in rcs]

    #
    # obtain existing runs
    #

    log.info('Obtain existing runs')
    db_handler = DB_Handler(db_path='extra/structural_analysis/results/results.sqlite')
    existing_identifiers = set(db_handler.list_identifiers())

    existing = []
    required = []
    no_rsn_available = []
    durations = {}
    rsns = {}

    def construct_identifier(
        archetype,
        suite,
        pulse,
        hazard_level,
        ground_motion,
        dt,
        direction,
        progress,
        damping,
    ):
        return '::'.join(
            [
                archetype,
                suite,
                pulse,
                hazard_level,
                ground_motion,
                dt,
                direction,
                progress,
                damping,
            ]
        )

    def construct_arguments(identifier):
        return identifier.split('::')

    for arch in cases:
        for suite in suites:
            if suite == 'cms':
                pulse_cases = ['True', 'False']
            else:
                pulse_cases = ['False']
            for pulse in pulse_cases:
                if suite == 'cs':
                    gms = ground_motions
                else:
                    if pulse == 'True':
                        gms = ground_motions_pulse
                    else:
                        gms = ground_motions_cms
                for hz, gm, dr in product(hazard_levels, gms, directions):
                    identifier = construct_identifier(
                        arch, suite, pulse, hz, gm, '0.001', dr, 'False', 'modal'
                    )
                    if identifier in existing_identifiers:
                        existing.append(identifier)
                    else:
                        required.append(identifier)

    other = []
    check_set = set(existing + required)
    for identifier in tqdm(existing_identifiers):
        if identifier not in check_set:
            other.append(identifier)
    for identifier in other:
        assert identifier[-2] == '_'
    # All of these are duplicate results. Will clean up.

    #
    # get ground motion duration
    #
    log.info('Get ground motion durations')

    def split_archetype(archetype):
        system, stories, rc = archetype.split('_')
        stories = int(stories)
        return system, stories, rc

    df_record_dict = {
        'cs': pd.read_csv(
            "extra/structural_analysis/results/site_hazard/"
            "required_records_and_scaling_factors_cs.csv",
            index_col=[0, 1, 2],
        )
        .sort_index(axis=0)
        .sort_index(axis=1),
        'cms': pd.read_csv(
            "extra/structural_analysis/results/site_hazard/ground_motions_cms.csv",
            index_col=[0, 1, 2, 3, 4],
        )
        .sort_index(axis=0)
        .sort_index(axis=1),
    }

    for identifier in tqdm(required):
        (
            archetype,
            suite,
            pulse,
            hazard_level,
            ground_motion,
            dt,
            direction,
            _,
            _,
        ) = construct_arguments(identifier)
        if pulse == 'False':
            pulse_bool = False
        else:
            pulse_bool = True
        if suite == 'cs':
            df_records = df_record_dict['cs']
            rsn = int(
                df_records.at[
                    (archetype, f"hz_{hazard_level}", "RSN"), str(ground_motion)
                ]
            )
        elif suite == 'cms':
            df_records = df_record_dict['cms']
            rsn = df_records.loc[
                (*split_archetype(archetype), int(hazard_level), pulse_bool), 'rsn'
            ].to_list()[int(ground_motion) - 1]
        else:
            raise ValueError(f'Encountered invalid suite: {suite}')
        rsns[identifier] = rsn
        if rsn in durations:
            if durations[rsn] is None:
                no_rsn_available.append(identifier)
        else:
            try:
                gm_filename = retrieve_peer_gm_data(rsn)[0]
                gm_data = import_PEER(gm_filename)
                durations[rsn] = gm_data[-1, 0]
            except ValueError:
                no_rsn_available.append(identifier)
                durations[rsn] = None

    #
    # sort durations from highest to lowest to group tasks appropriately
    #
    log.info('Sorting durations')
    duration_series = pd.Series(
        [durations[rsns[idnt]] for idnt in required if idnt not in no_rsn_available],
        index=pd.Index([idnt for idnt in required if idnt not in no_rsn_available]),
    )

    duration_series.sort_values(ascending=False, inplace=True)

    #
    # Get an estimated simulation pacing ratio using the existing analyses
    #
    log.info('Estimating simulation pacing ratio')

    def process_identifier(identifier):
        _, log_file = db_handler.retrieve_metadata_only(identifier)
        return parse_log_and_calculate_ratio(log_file)

    def estimate_pacing_ratio():
        db_handler = DB_Handler(
            db_path='extra/structural_analysis/results/results.sqlite'
        )
        identifiers = db_handler.list_identifiers()
        # Initialize the ProcessPoolExecutor to use all available cores
        with ProcessPoolExecutor() as executor:
            # Submit tasks for processing each identifier
            futures = []
            for identifier in identifiers:
                future = executor.submit(process_identifier, identifier)
                futures.append(future)

            # Collect the results as they complete
            ratios = np.empty(len(identifiers))
            for i, future in enumerate(tqdm(futures)):
                ratios[i] = future.result()

        return ratios

    ratios = estimate_pacing_ratio()

    sns.ecdfplot(ratios)
    plt.show()

    # We'll use 80.

    #
    # Split identifires to groups to assign to jobs
    #
    real_duration_estimate = duration_series * 2.00 * 80.00

    num_nodes = 50
    num_cores = 48 * num_nodes
    num_hours = 48.00
    max_runtime = num_hours * 60.00 * 60.00 * num_cores

    groups = []

    duration_dict = real_duration_estimate.to_dict()

    while duration_dict:
        identifiers = []
        durations = []
        while True:
            # Get another item
            identifier, duration = duration_dict.popitem()
            # If we exceed the runtime
            if np.sum(durations) + duration > max_runtime:
                # put it back in and stop
                duration_dict[identifier] = duration
                break

            # Stop if we ran out of items
            if not duration_dict:
                break

            # otherwise keep adding to the group
            identifiers.append(identifier)
            durations.append(duration)

        # add the group to the list of groups
        groups.append(identifiers)

    print(len(groups))

    #
    # Generate slurm scripts and taskfiles
    #

    def generate_slurm_script(
        jobname: str, num_nodes: str, num_tasks: str, partition: str, time: str
    ) -> None:
        with open(
            'extra/structural_analysis/tacc/template.sh', 'r', encoding='utf-8'
        ) as f:
            contents = f.read()
        contents = contents.replace('%jobname%', jobname)
        contents = contents.replace('%num_nodes%', num_nodes)
        contents = contents.replace('%num_tasks%', num_tasks)
        contents = contents.replace('%partition%', partition)
        contents = contents.replace('%time%', time)
        with open(
            f'extra/structural_analysis/tacc/{jobname}.sh', 'w', encoding='utf-8'
        ) as f:
            f.write(contents)

    for i, group in enumerate(tqdm(groups)):
        i_group = i + 1
        with open(
            f'extra/structural_analysis/tacc/{date_prefix}_nlth_group_{i_group}_taskfile',
            'w',
            encoding='utf-8',
        ) as file:
            for identifier in group:
                (
                    archetype,
                    suite,
                    pulse,
                    hazard_level,
                    ground_motion,
                    dt,
                    direction,
                    _,
                    _,
                ) = construct_arguments(identifier)
                dt = '0.001'
                command = (
                    f"python extra/structural_analysis/src/"
                    f"structural_analysis/response_2d.py "
                    f"'--archetype' '{archetype}' "
                    f"'--suite_type' '{suite}' "
                )
                if pulse == 'True':
                    command += "'--pulse' "
                command += (
                    f"'--hazard_level' '{hazard_level}' "
                    f"'--gm_number' '{ground_motion}' "
                    f"'--analysis_dt' '{dt}' "
                    f"'--direction' '{direction}' "
                    f"'--group_id' '{i_group}' "
                    f"\n"
                )
                file.write(command)
        generate_slurm_script(
            f'{date_prefix}_nlth_group_{i_group}',
            f'{num_nodes}',
            f'{num_cores}',
            'skx',
            f'{int(num_hours)}:00:00',
        )


def parse_log_and_calculate_ratio(log: str) -> float:
    # Regular expression to match the timestamps and relevant log entries
    assert 'Analysis started' in log
    assert 'Analysis finished' in log
    timestamp_pattern = r'(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2} [AP]M)'
    ground_motion_pattern = r'Ground Motion Duration: ([\d.]+) s'

    # Find all timestamps
    timestamps = re.findall(timestamp_pattern, log)

    # Convert timestamps to datetime objects
    datetime_format = '%m/%d/%Y %I:%M:%S %p'
    datetimes = [datetime.strptime(ts, datetime_format) for ts in timestamps]

    # Find ground motion duration
    ground_motion_match = re.search(ground_motion_pattern, log)
    ground_motion_duration = (
        float(ground_motion_match.group(1)) if ground_motion_match else 0
    )

    # Find start and end timestamps for the analysis
    start_time = datetimes[0]
    end_time = datetimes[-1]

    # Calculate the runtime in seconds
    runtime_seconds = (end_time - start_time).total_seconds()

    # Calculate the ratio of ground motion duration to total runtime
    ratio = runtime_seconds / ground_motion_duration

    return ratio
