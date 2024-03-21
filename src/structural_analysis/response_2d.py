"""
Run nonlinear time-history analysis to get the building's response
"""

import importlib
import argparse
from typing import Union
import numpy as np
import pandas as pd
from osmg import solver
from osmg.gen.query import ElmQuery
from osmg.ground_motion_utils import import_PEER
from src.util import store_info
from extra.structural_analysis.src.util import retrieve_peer_gm_data

# ~~~~~~~~~~~~~~~~~~~~~~ #
# set up argument parser #
# ~~~~~~~~~~~~~~~~~~~~~~ #

parser = argparse.ArgumentParser()
parser.add_argument("--archetype")
parser.add_argument("--suite_type")
parser.add_argument("--pulse", default=False)
parser.add_argument("--hazard_level")
parser.add_argument("--gm_number")
parser.add_argument("--analysis_dt")
parser.add_argument("--direction")
parser.add_argument("--output_dir_name", default='individual_files')
parser.add_argument("--progress_bar", default=False)
parser.add_argument('--custom_path', default=None)
parser.add_argument('--damping', default='modal')

args = parser.parse_args()
archetype = args.archetype
suite_type = args.suite_type
pulse = args.pulse
hazard_level = args.hazard_level
gm_number = int(args.gm_number)
analysis_dt = float(args.analysis_dt)
direction = args.direction
output_dir_name = args.output_dir_name
progress_bar = bool(args.progress_bar)
custom_path = args.custom_path
damping = args.damping

# # debugging
# archetype = 'scbf_9_ii'
# suite_type = 'cms'
# pulse = False
# hazard_level = '4'
# gm_number = 2
# analysis_dt = 0.01
# direction = 'y'
# output_dir_name = 'individual_files'
# progress_bar = True
# custom_path = '/tmp/test'
# damping = 'modal'

def split_archetype(archetype):
    system, stories, rc = archetype.split('_')
    stories = int(stories)
    return system, stories, rc

# load archetype building
archetypes_module = importlib.import_module(
    "extra.structural_analysis.src.structural_analysis.archetypes_2d"
)
try:
    archetype_builder = getattr(archetypes_module, archetype)
except AttributeError as exc:
    raise ValueError(f"Invalid archetype code: {archetype}") from exc

mdl, loadcase = archetype_builder(direction)

# from osmg.graphics.preprocessing_3d import show
# show(mdl, loadcase, extrude=True)

num_levels = len(mdl.levels) - 1
level_heights = np.diff([level.elevation for level in mdl.levels.values()])

lvl_nodes = []
base_node = list(mdl.levels[0].nodes.values())[0].uid
lvl_nodes.append(base_node)

for i in range(num_levels):
    lvl_nodes.append(loadcase.parent_nodes[i + 1].uid)

specific_nodes = lvl_nodes + [n.uid for n in mdl.levels[0].nodes.values()]
# also add the leaning column nodes due to their rotational restraints
eqr = ElmQuery(mdl)
for lvl in range(num_levels):
    nd = eqr.search_node_lvl(0.00, 0.00, lvl + 1)
    assert nd is not None
    specific_nodes.append(nd.uid)

if suite_type == 'cs':
    df_records = pd.read_csv(
        "extra/structural_analysis/results/site_hazard/"
        "required_records_and_scaling_factors_cs.csv",
        index_col=[0, 1, 2],
    )

    rsn = int(
        df_records.at[(archetype, f"hz_{hazard_level}", "RSN"), str(gm_number)]
    )
    scaling = df_records.at[
        (archetype, f"hz_{hazard_level}", "SF"), str(gm_number)
    ]

    dir_idx = {"x": 0, "y": 1}
    try:
        gm_filename = retrieve_peer_gm_data(rsn)[dir_idx[direction]]
    except ValueError:
        raise ValueError(f'RSN {rsn} not available.')
    gm_data = import_PEER(gm_filename)
    gm_dt = gm_data[1, 0] - gm_data[0, 0]
    ag = gm_data[:, 1] * scaling

elif suite_type == 'cms':
    df_records = pd.read_csv(
        "extra/structural_analysis/results/site_hazard/"
        "ground_motions_cms.csv",
        index_col=[0, 1, 2, 3, 4],
    )

    rsn = df_records.loc[
        (*split_archetype(archetype), int(hazard_level), pulse), 'rsn'
    ].to_list()[gm_number]
    scaling = df_records.loc[
        (*split_archetype(archetype), int(hazard_level), pulse), 'scaling'
    ].to_list()[gm_number]

    dir_idx = {"x": 0, "y": 1}
    try:
        gm_filename = retrieve_peer_gm_data(rsn)[dir_idx[direction]]
    except ValueError:
        raise ValueError(f'RSN {rsn} not available.')
    gm_data = import_PEER(gm_filename)
    gm_dt = gm_data[1, 0] - gm_data[0, 0]
    ag = gm_data[:, 1] * scaling

else:
    raise NotImplementedError(f'Unsupported suite type: {suite_type}')

if custom_path:
    output_folder = custom_path
else:
    output_folder = (
        f"extra/structural_analysis/results/{archetype}/"
        f"{output_dir_name}/{hazard_level}/gm{gm_number}"
    )

# from osmg.graphics.preprocessing_3d import show
# show(mdl, loadcase, extrude=True)
# show(mdl, loadcase, extrude=False)

#
# modal analysis
#

modal_analysis = solver.ModalAnalysis(
    mdl, {loadcase.name: loadcase}, num_modes=num_levels * 6
)
modal_analysis.settings.store_forces = False
modal_analysis.settings.store_fiber = False
modal_analysis.settings.restrict_dof = [False, True, False, True, False, True]
modal_analysis.run()

periods = modal_analysis.results[loadcase.name].periods
assert periods is not None

# from osmg.graphics.postprocessing_3d import show_deformed_shape
# show_deformed_shape(
#     modal_analysis, loadcase.name, 0, 0.00,
#     extrude=False, animation=False)

# mnstar = modal_analysis.modal_participation_factors(loadcase.name, 'x')[1]
# np.cumsum(mnstar)

#
# time-history analysis
#

t_bar = periods[0]

if damping == "rayleigh":
    damping_input = {
        "type": "rayleigh",
        "ratio": 0.02,
        "periods": [t_bar, t_bar / 10.00],
    }
elif damping == "modal":
    damping_input = {
        "type": "modal+stiffness",
        "num_modes": (num_levels) * 3,
        "ratio_modal": 0.02,
        "period": t_bar / 10.00,
        "ratio_stiffness": 0.001,
    }
else:
    raise ValueError(f"Invalid damping type: {damping}")

nlth = solver.THAnalysis(mdl, {loadcase.name: loadcase})
nlth.output_directory = output_folder
nlth.settings.log_file = store_info(
    f"{output_folder}/log_{direction}", [gm_filename]
)
nlth.settings.restrict_dof = [False, True, False, True, False, True]
nlth.settings.store_fiber = False
nlth.settings.store_forces = False
nlth.settings.store_reactions = True
nlth.settings.store_release_force_defo = False
# nlth.settings.specific_nodes = specific_nodes

nlth.run(
    analysis_dt,
    ag,
    None,
    None,
    gm_dt,
    damping=damping_input,
    print_progress=progress_bar,
    drift_check=0.10,  # 10% drift
    time_limit=47.95,  # hours
    dampen_out_residual=True,
    finish_time=0.00,  # means run the entire file
)

# store response quantities

df = pd.DataFrame()
df["time--"] = np.array(nlth.time_vector)

df["Rtime--"] = np.array(nlth.results[loadcase.name].clock)
df["Rtime--"] -= df["Rtime--"].iloc[0]
df["Subdiv--"] = np.array(nlth.results[loadcase.name].subdivision_level)

if direction == "x":
    j = 1
elif direction == "y":
    j = 2
else:
    raise ValueError(f"Invalid direction: {direction}")

for lvl in range(num_levels + 1):
    df[f"FA-{lvl}-{j}"] = nlth.retrieve_node_abs_acceleration(
        lvl_nodes[lvl], loadcase.name
    ).loc[:, "abs ax"]
    df[f"FV-{lvl}-{j}"] = nlth.retrieve_node_abs_velocity(
        lvl_nodes[lvl], loadcase.name
    ).loc[:, "abs vx"]
    if lvl > 0:
        us = nlth.retrieve_node_displacement(lvl_nodes[lvl], loadcase.name).loc[
            :, "ux"
        ]
        if lvl == 1:
            dr = us / level_heights[lvl - 1]
        else:
            us_prev = nlth.retrieve_node_displacement(
                lvl_nodes[lvl - 1], loadcase.name
            ).loc[:, "ux"]
            dr = (us - us_prev) / level_heights[lvl - 1]
        df[f"ID-{lvl}-{j}"] = dr

df[f"Vb-0-{j}"] = nlth.retrieve_base_shear(loadcase.name)[:, 0]

df.columns = pd.MultiIndex.from_tuples(
    [x.split("-") for x in df.columns.to_list()]
)
df.sort_index(axis=1, inplace=True)

df.to_parquet(
    store_info(f"{output_folder}/results_{direction}.parquet", [gm_filename])
)
