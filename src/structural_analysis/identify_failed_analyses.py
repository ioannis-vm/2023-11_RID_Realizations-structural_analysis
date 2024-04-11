"""

- Moves misplaced analysis results (due to bug in the output file
  name)
- Identifies time-history analyses that failed and moves them to a
  separate location
- Prepares SLURM files with the analyses to repeat

"""

import os
import re
from pathlib import Path
import shutil
from tqdm import tqdm
import pandas as pd
from extra.structural_analysis.src.structural_analysis.analysis_stats import (
    status_from_log,
    get_logtime,
    get_max_subdiv_reported,
)

# We don't want this file to be type-checked.
# mypy: ignore-errors


# Find the files. This takes a long time.


def scan_dir(path):
    for entry in os.scandir(path):
        if entry.is_dir(follow_symlinks=False):
            yield from scan_dir(entry.path)
        else:
            yield entry.path


def get_files():
    all_files = []
    for file_path in scan_dir(results_base_path):
        if '.trash' not in file_path:
            all_files.append(file_path)

    # split them based on file name
    def get_name(path):
        return Path(path).name

    grouped_files = {}
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


desired_names = [
    'log_x',
    'log_y',
    'log_x.info',
    'log_y.info',
    'results_x.parquet',
    'results_y.parquet',
    'results_x.parquet.info',
    'results_y.parquet.info',
]

results_base_path = Path('/tmp/zip4/results/')

grouped_files = get_files()

#
# remove info files that don't have an actual file
#


def trash(file, reason=None):
    key_str = '/tmp/zip4/results/'
    assert key_str in str(file)
    new_path = Path(str(file).replace(key_str, key_str + '.trash/'))
    os.makedirs(new_path.parent)
    shutil.move(file, new_path)
    if reason:
        reason_file = new_path.with_name(new_path.name + '.trashinfo')
        with open(reason_file, 'w', encoding='utf-8') as f:
            f.write(reason + '\n')


info_but_missing = []
print(desired_names)
for desired_name in desired_names:
    if not desired_name.endswith('.info'):
        continue
    print(desired_name)
    files = grouped_files[desired_name]
    for file in tqdm(files):
        filep = Path(file)
        info_path = filep.with_name(filep.name.replace('.info', ''))
        if not info_path.exists():
            info_but_missing.append(info_path)
            files.remove(file)
            trash(file, reason='Info file exists but there is no actual file.')

# now all .info files in `grouped_files` have a corresponding file

#
# parse command from `.info` and move files to the right location
#


def extract_command_line_arguments(info_file):
    pattern = re.compile(r'^Command line arguments: (.+)$', re.M)

    with open(info_file, 'r') as file:
        contents = file.read()

    match_obj = pattern.search(contents)
    assert match_obj
    return match_obj.group(1).split(' ')[1::]


def get_neighbor_element(lst, ref_element, position='after'):
    """
    Get the element before or after a specified element in a list.

    """
    if ref_element not in lst:
        return None

    index = lst.index(ref_element)

    if position == 'before':
        return lst[index - 1] if index > 0 else None
    elif position == 'after':
        return lst[index + 1] if index < len(lst) - 1 else None
    else:
        raise ValueError("position must be 'before' or 'after'")


arguments = {}
for desired_name in desired_names:
    if not desired_name.endswith('.info'):
        continue
    print(desired_name)
    files = grouped_files[desired_name]
    for file in tqdm(files):
        arguments[file] = extract_command_line_arguments(file)


# dill.dump_session('session.pcl')


list(arguments.keys())[0]
list(arguments.values())[2]

#
# Considering the specified arguments, move the files to the right
# location
#

# Turn the arguments to a dictionary for easier parsing


def args_to_dict(argument_list):
    arg_dict = {}
    for i, arg in enumerate(argument_list):
        if arg.startswith('--'):
            key = arg.replace('--', '')
            if i + 1 == len(argument_list) or argument_list[i + 1].startswith('--'):
                value = True
            else:
                value = argument_list[i + 1]
            arg_dict[key] = value
    return arg_dict


for key, value in tqdm(arguments.items()):
    arguments[key] = args_to_dict(value)


# Correct the output folder

for key, value in tqdm(arguments.items()):
    dr = value['output_dir_name']
    tp = value['suite_type']
    value['output_dir_name'] = dr.replace('_cs', '_' + tp)


# Move files

arguments_processed = {}
for key, value in tqdm(arguments.items()):
    if key in arguments_processed:
        continue
    arguments_processed[key] = value

    # original location
    original_dir = Path(key).parent
    filename = Path(key).name
    this_file = Path(key)
    other_file = Path(key).with_name(filename.replace('.info', ''))

    # variables
    archetype = value['archetype']
    dirname = value['output_dir_name']
    hz = value['hazard_level']
    gm = value['gm_number']
    pulse = value.get('pulse', False)
    if pulse:
        dirname = dirname.replace('cms', 'pulse')

    # new location
    new_dir = Path(f'/tmp/zip4/results/{archetype}/{dirname}/{hz}/{gm}/')
    # create directory
    os.makedirs(new_dir, exist_ok=True)

    # move the files
    shutil.move(str(this_file), str(new_dir))
    shutil.move(str(other_file), str(new_dir))


#
# determine analyses that didn't finish, move them to a different directory
#

# (merge results with rsync)
desired_names = [
    'log_x',
    'log_y',
    'log_x.info',
    'log_y.info',
    'results_x.parquet',
    'results_y.parquet',
    'results_x.parquet.info',
    'results_y.parquet.info',
]

results_base_path = Path('/tmp/zip4/results/')

grouped_files = get_files()

log_files = []
log_files.extend(grouped_files['log_x'])
log_files.extend(grouped_files['log_y'])

log_file = log_files[0]


def key_from_path(log_file):
    parts = log_file.split('/')
    dr = parts[-1][-1]
    gm = parts[-2]
    hz = parts[-3]
    target = parts[-4].split('_')[-1]
    syst = parts[-5].split('_')[0]
    stor = parts[-5].split('_')[1]
    rc = parts[-5].split('_')[2]
    return (target, syst, stor, rc, hz, gm, dr)


def path_from_key(key):
    target, syst, stor, rc, hz, gm, dr = key
    archetype = '_'.join([syst, stor, rc])
    basedir = '/tmp/zip4/results'
    return f'{basedir}/{archetype}/20240311_individual_files_{target}/{hz}/{gm}/log_{dr}'


keys = []
values = {
    'status': [],
    'start_time': [],
    'end_time': [],
    'maxsub': [],
}
for log_file in tqdm(log_files):
    keys.append(key_from_path(log_file))
    values['status'].append(status_from_log(log_file))
    values['start_time'].append(get_logtime(log_file, 0))
    values['end_time'].append(get_logtime(log_file, -1))
    values['maxsub'].append(get_max_subdiv_reported(log_file))

df = pd.DataFrame(values, index=pd.MultiIndex.from_tuples(keys))
df['duration'] = df['end_time'] - df['start_time']

# status_df = df['status']
# status_df.value_counts()

# df['duration'].describe()
# from datetime import timedelta
# df.loc[:, ['duration', 'maxsub']][
#     df['duration'] > timedelta(days=0, hours=1, minutes=0)
# ]

# move those that failed to converge

# dirs = glob(f'/tmp/zip4/results_noconverge/*/*/*/*/*')
# old = dirs[0]
# for old in dirs[1:]:
#     new = '/'.join(old.split('/')[:-2]).replace(
#         'results_noconverge', 'results_noconverge_x'
#     )
#     os.makedirs(new, exist_ok=True)
#     shutil.move(old, new)

processed = []
for key in tqdm(df[df['status'] == 'failed to converge'].index):
    if key in processed:
        continue
    path = str(Path(path_from_key(key)).parent) + '/'
    new_path = path.replace('/results/', '/results_noconverge/')[:-1]  # fix
    # careful!! new path's directory should not have the folder name.
    if (os.path.exists(path)) and (not os.path.exists(new_path)):
        os.makedirs(new_path)
        shutil.move(path, new_path)
    processed.append(key)

# remove those that are showing as running
processed = []
for key in tqdm(df[df['status'] == 'running'].index):
    if key in processed:
        continue
    path = str(Path(path_from_key(key)).parent) + '/'
    if os.path.exists(path):
        shutil.rmtree(path)
    processed.append(key)

# dataframe
df.to_pickle('/tmp/zip4/records.pcl')

#
# prepare slurm scripts for the remaining analyses
#


# dill.dump_session('session.pcl')
# dill.load_session('session.pcl')
