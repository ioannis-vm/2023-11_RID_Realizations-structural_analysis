"""
Script used to query the status of ongoing analyses while SLURM jobs
are in progress.
"""


from __future__ import annotations
import os
from pathlib import Path
from tqdm import tqdm
import numpy as np
import pandas as pd
from extra.structural_analysis.src.db import DB_Handler


def main():
    db_handler = DB_Handler(
        db_path=Path('extra/structural_analysis/results/results.sqlite')
    )
    identifiers = db_handler.list_identifiers()

    # additional results dumped in results/ directory
    dir_identifiers = []
    for identifier in os.listdir('extra/structural_analysis/results/'):
        if '::' not in identifier:
            continue
        dir_identifiers.append(identifier)

    identifiers.extend(dir_identifiers)

    # remove dt parameter
    new_identifiers = []
    for identifier in identifiers:
        parts = identifier.split('::')
        assert len(parts) == 9
        new_identifier = '::'.join(
            [
                parts[0],
                parts[1],
                parts[2],
                parts[3],
                parts[4],
                parts[6],
            ]
        )
        new_identifiers.append(new_identifier)
    identifier_set = set(new_identifiers)

    taskfile_to_check = (
        'extra/structural_analysis/tacc/20240411/20240411_nlth_group_15_taskfile'
    )
    with open(taskfile_to_check, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    check = np.empty(len(lines), dtype=bool)
    available_identifiers = []
    for i, line in enumerate(lines):
        line = line.replace("'", "").split(' ')
        arguments = line[2:]
        args_dictionary = args_to_dict(arguments)
        new_identifier = '::'.join(
            [
                args_dictionary['archetype'],
                args_dictionary['suite_type'],
                args_dictionary.get('pulse', 'False'),
                args_dictionary['hazard_level'],
                args_dictionary['gm_number'],
                args_dictionary['direction'],
            ]
        )
        check[i] = new_identifier in identifier_set
        if check[i] == True:
            available_identifiers.append(new_identifier)
    print(pd.Series(check).value_counts())

    # read logs and determine if analysis converged without any issues
    db_identifier_lists = [x.split('::') for x in identifiers]
    available_identifier_lists = [x.split('::') for x in available_identifiers]
    available_db_identifier_lists = []
    for available_identifier_list in available_identifier_lists:
        for db_identifier_list in db_identifier_lists:
            if (
                available_identifier_list[0] == db_identifier_list[0]
                and available_identifier_list[1] == db_identifier_list[1]
                and available_identifier_list[2] == db_identifier_list[2]
                and available_identifier_list[3] == db_identifier_list[3]
                and available_identifier_list[4] == db_identifier_list[4]
                and available_identifier_list[5] == db_identifier_list[6]
            ):
                available_db_identifier_lists.append(db_identifier_list)

    available_db_identifiers = ['::'.join(x) for x in available_db_identifier_lists]

    finished_bool = np.empty(len(available_db_identifiers), dtype=bool)
    for i, available_db_identifier in enumerate(tqdm(available_db_identifiers)):
        info, log = db_handler.retrieve_metadata_only(available_db_identifier)
        if (
            'failed to converge' not in log
            and 'Analysis started' in log.split('\n')[0]
            and 'Analysis finished' in log.split('\n')[-2]
        ):
            finished_bool[i] = True
        else:
            finished_bool[i] = False
    print(pd.Series(finished_bool).value_counts())


def args_to_dict(argument_list: list[str]) -> dict[str, str]:
    """
    Converts a list of command line arguments into a dictionary.
    Takes care of boolean flags that only have a `--something` entry.
    """
    arg_dict = {}
    for i, arg in enumerate(argument_list):
        if arg.startswith('--'):
            key = arg.replace('--', '')
            if i + 1 == len(argument_list) or argument_list[i + 1].startswith('--'):
                value = 'True'
            else:
                value = argument_list[i + 1]
            arg_dict[key] = value
    return arg_dict


def format_record_id(args_dictionary):
    record_id = '::'.join(
        [
            str(x)
            for x in [
                args_dictionary['archetype'],
                args_dictionary['suite_type'],
                args_dictionary.get('pulse', False),
                args_dictionary['hazard_level'],
                args_dictionary['gm_number'],
                args_dictionary['analysis_dt'],
                args_dictionary['direction'],
                args_dictionary.get('progress_bar', False),
                args_dictionary.get('damping', 'modal'),
            ]
        ]
    )
    return record_id
