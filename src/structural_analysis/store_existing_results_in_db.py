"""
Store results created before introducing database storage into a
database.


This file is intended for one-time use to migrate the existing results
to the database.


Created: Tue Apr  9 12:07:57 CDT 2024
Modified to run locally: Thu Apr 11 04:51:37 AM PDT 2024

"""

from __future__ import annotations
from typing import Any
from typing import Generator
import os
import re
import shutil
from pathlib import Path
from tqdm import tqdm
import pandas as pd
from extra.structural_analysis.src.db import DB_Handler


def main():
    #
    # Identify existing result files
    #

    desired_names = [
        'results_x.parquet',
        'results_y.parquet',
    ]

    results_base_path = 'extra/structural_analysis/results/'
    all_files = get_files(desired_names, results_base_path)

    # join the lists
    all_files_list = all_files['results_y.parquet'] + all_files['results_x.parquet']

    # turn strings into paths
    file_paths = [Path(x) for x in all_files_list]
    file_paths_log = [
        Path(x).with_name(x.name.replace('results', 'log').replace('.parquet', ''))
        for x in file_paths
    ]
    file_paths_info = [Path(x).with_name(x.name + '.info') for x in file_paths_log]

    for file, log_file, info_file in tqdm(
        zip(file_paths, file_paths_log, file_paths_info)
    ):
        assert log_file.exists()
        assert info_file.exists()

    #
    # Store the results in a database
    #

    # initialize DB handler
    db_handler = DB_Handler(db_path=Path(f'{results_base_path}/results.sqlite'))

    for file, log_file, info_file in tqdm(
        zip(file_paths, file_paths_log, file_paths_info), total=len(file_paths)
    ):
        args = extract_command_line_arguments(str(info_file))
        args_dictionary = args_to_dict(args)

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
        df = pd.read_parquet(str(file))
        with open(info_file, 'r', encoding='utf-8') as f:
            info = f.read()
        with open(log_file, 'r', encoding='utf-8') as f:
            log_contents = f.read()
        db_handler.store_data(
            identifier=record_id,
            dataframe=df,
            metadata=info,
            log_content=log_contents,
        )


def scan_dir(path: str) -> Generator:
    """
    Scans a directory recursively
    """
    for entry in os.scandir(path):
        if entry.is_dir(follow_symlinks=False):
            yield from scan_dir(entry.path)
        else:
            yield entry.path


def get_files(desired_names, base_path) -> dict[str, list[str]]:
    """
    Scans a directory to retrieve files
    """
    all_files = []
    for file_path in scan_dir(base_path):
        if '.trash' not in file_path:
            all_files.append(file_path)

    grouped_files: dict[str, list[str]] = {}
    for name in desired_names:
        grouped_files[name] = []
    grouped_files['other'] = []
    for file in all_files:
        found = False
        for name in desired_names:
            if file.endswith(name):
                found = True
                grouped_files[name].append(file)
        if found is False:
            grouped_files['other'].append(file)

    return grouped_files


def update_path(file_path: Path, origin, destination: str) -> Path:
    """
    Updates a given path to replace the corresponding file system.
    """
    return Path(str(file_path).replace(origin, destination))


def pbar_func(obj: Any, progress_msg: str) -> Any:
    """
    Return a progress bar function
    """
    if progress_msg:
        print(progress_msg)
        return tqdm(list(obj))
    return obj


def create_dirs(file_paths: list[Path], progress_msg='') -> None:
    """
    Given a list of paths, creates directories if they don't already
    exist.
    """

    for path in pbar_func(file_paths, progress_msg):
        path.mkdir(parents=True, exist_ok=True)


def copy_files(
    origin_paths: list[Path], destination_paths: list[Path], progress_msg=''
) -> None:
    """
    Copies files over.
    """

    assert len(origin_paths) == len(destination_paths)
    for origin, destination in pbar_func(
        zip(origin_paths, destination_paths), progress_msg
    ):
        try:
            shutil.copy(origin, destination)
        except FileNotFoundError:
            if 'log' in origin.name:
                result_file = origin.with_name(
                    origin.name.replace('log', 'results') + '.parquet'
                )
                info_file = origin.with_name(origin.name + '.info')
                res_info_file = result_file.with_name(result_file.name + '.info')
                for thing in [result_file, info_file, res_info_file]:
                    if thing.exists():
                        print(f'Removing {thing}')
                        os.remove(thing)


def extract_command_line_arguments(info_file: str) -> list[str]:
    """
    Extracts the command line arguments listed in an `.info` file
    """
    pattern = re.compile(r'^Command line arguments: (.+)$', re.M)

    with open(info_file, 'r', encoding='utf-8') as file:
        contents = file.read()

    match_obj = pattern.search(contents)
    assert match_obj
    return match_obj.group(1).split(' ')[1::]


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
