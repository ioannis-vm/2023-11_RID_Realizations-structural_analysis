"""
Run nonlinear time-history analysis to get the building's response
"""

from pathlib import Path
import os
import importlib
import argparse
import pickle
import numpy as np
import pandas as pd
from osmg import solver
from osmg.gen.query import ElmQuery
from osmg.ground_motion_utils import import_PEER
from src.util import store_info
from extra.structural_analysis.src.util import retrieve_peer_gm_data
from extra.structural_analysis.src.db import DB_Handler


def obtain_edps(dataframe):
    """
    Extracts the EDPs from a dataframe containing the full
    time-history analysis results.
    The EDPs are `PFA`, `PFV`, `PID`, and `RID`.

    Parameters
    ----------
    dataframe: pd.DataFrame
        Dataframe containing the full time-hisotyr analysis results.

    Returns
    -------
    pd.DataFrame
        Dataframe containing the EDPs

    """
    edps = dataframe.abs().max().drop(['Rtime', 'Subdiv', 'Vb'])
    edps['FA'] /= 386.22
    edps.index = pd.MultiIndex.from_tuples(
        [(f'P{x[0]}', x[1], x[2]) for x in edps.index]
    )
    rid = dataframe.iloc[-1, :]['ID'].abs()
    rid.index = pd.MultiIndex.from_tuples([('RID', x[0], x[1]) for x in rid.index])
    edps = pd.concat((edps, rid), axis=0)
    return edps


def main():
    # ~~~~~~~~~~~~~~~~~~~~~~ #
    # set up argument parser #
    # ~~~~~~~~~~~~~~~~~~~~~~ #

    # import sys
    # sys.argv = [
    #     "python",
    #     "--archetype",
    #     "brbf_3_iv",
    #     "--suite_type",
    #     "cs",
    #     "--hazard_level",
    #     "29",
    #     "--gm_number",
    #     "1",
    #     "--analysis_dt",
    #     "0.001",
    #     "--direction",
    #     "x",
    #     '--damping',
    #     "modal",
    #     '--scaling',
    #     "1.00",
    #     '--group_id',
    #     '99999',
    # ]

    parser = argparse.ArgumentParser()
    parser.add_argument('--archetype')
    parser.add_argument('--suite_type')
    parser.add_argument('--hazard_level')
    parser.add_argument('--gm_number')
    parser.add_argument('--analysis_dt')
    parser.add_argument('--direction')
    parser.add_argument('--damping')
    parser.add_argument('--scaling')
    parser.add_argument('--group_id')
    parser.add_argument('--no_LLRS', action='store_true')

    args = parser.parse_args()
    archetype = args.archetype
    suite_type = args.suite_type
    hazard_level = args.hazard_level
    gm_number = int(args.gm_number)
    analysis_dt = float(args.analysis_dt)
    direction = args.direction
    damping = args.damping
    additional_scaling = float(args.scaling)
    group_id = int(args.group_id)
    no_llrs = args.no_LLRS

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

    mdl, loadcase = archetype_builder(direction, no_llrs=no_llrs)

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
        scaling = df_records.at[(archetype, f"hz_{hazard_level}", "SF"), str(gm_number)]

        dir_idx = {"x": 0, "y": 1}
        try:
            gm_filename = retrieve_peer_gm_data(rsn)[dir_idx[direction]]
        except ValueError as exc:
            raise ValueError(f'RSN {rsn} not available.') from exc
        gm_data = import_PEER(gm_filename)
        gm_dt = gm_data[1, 0] - gm_data[0, 0]
        ag = gm_data[:, 1] * scaling

    else:
        # Note: we examined CMS suites and decided not to use them.
        raise NotImplementedError(f'Unsupported suite type: {suite_type}')

    ag *= additional_scaling

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

    identifier = '::'.join(
        [
            str(x)
            for x in [
                archetype,
                suite_type,
                hazard_level,
                gm_number,
                analysis_dt,
                direction,
                damping,
                additional_scaling,
            ]
        ]
    )
    os.makedirs('/tmp/osmg_logs/', exist_ok=True)
    log_file = f'/tmp/osmg_logs/{identifier}'

    nlth = solver.THAnalysis(mdl, {loadcase.name: loadcase})
    nlth.settings.log_file = log_file
    nlth.settings.restrict_dof = [False, True, False, True, False, True]
    nlth.settings.store_fiber = False
    nlth.settings.store_forces = False
    nlth.settings.store_reactions = True
    nlth.settings.store_release_force_defo = False
    nlth.settings.specific_nodes = specific_nodes

    # we want to store results at a resolution of 0.01s
    # to avoid running out of memory
    assert analysis_dt <= 0.01
    skip_steps = int(0.01 / analysis_dt)

    metadata = nlth.run(
        analysis_dt,
        ag,
        None,
        None,
        gm_dt,
        damping=damping_input,
        print_progress=False,
        drift_check=0.10,  # 10% drift
        skip_steps=skip_steps,  # only save after X converged states
        time_limit=47.95,  # hours
        dampen_out_residual=True,
        finish_time=0.00,  # means run the entire file
    )

    # get log contents
    with open(log_file, 'r', encoding='utf-8') as file:
        log_contents = file.read()
    # get session metadata

    success = metadata['analysis_finished_successfully']

    # Termination due to drift is a successful analysis.
    # (osmg marks them as failed)
    if 'due to excessive drift' in log_contents:
        success = True

    if success:
        sub_path = ''
    else:
        sub_path = 'failed/'
    info = store_info(input_data_paths=[gm_filename])

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

    df.columns = pd.MultiIndex.from_tuples([x.split("-") for x in df.columns.to_list()])
    df.sort_index(axis=1, inplace=True)

    df = df.set_index('time')
    # pylint: disable=unsubscriptable-object
    df = df[~df.index.duplicated()]

    # interpoate to a time step of 0.01 (to save space)
    # and set index to `time`
    step = 0.01
    new_index = np.arange(df.index.min(), df.index.max() + step, step)
    df_resampled = pd.DataFrame(index=new_index, columns=df.columns)
    df_resampled.index.name = df.index.name
    for col in df.columns:
        df_resampled[col] = np.interp(new_index, df.index.values, df[col].values)

    # add the results to the database
    if not os.path.isdir(f'extra/structural_analysis/results/{sub_path}'):
        os.makedirs(f'extra/structural_analysis/results/{sub_path}')
    db_handler = DB_Handler(
        db_path=f'extra/structural_analysis/results/{sub_path}results_{group_id}.sqlite'
    )
    try:
        db_handler.store_data(
            identifier=identifier,
            dataframe=df_resampled,
            metadata=info,
            log_content=log_contents,
        )
    except:  # noqa: E722, pylint: disable=bare-except
        # if it fails *for any reason*, pickle the result variables and save them
        # with a unique name
        out = {
            'identifier': identifier,
            'dataframe': df_resampled,
            'metadata': info,
            'log_content': log_contents,
        }
        with open(
            Path(f'extra/structural_analysis/results/{sub_path}{identifier}'), 'wb'
        ) as f:
            pickle.dump(out, f)

    # add EDP results to the database
    edp_db_handler = DB_Handler(
        db_path=(
            f'extra/structural_analysis/results/'
            f'{sub_path}edp_results_{group_id}.sqlite'
        )
    )
    edps = obtain_edps(df)
    try:
        edp_db_handler.store_data(identifier, edps, '', '')
    except:  # noqa: E722, pylint: disable=bare-except
        # if it fails *for any reason*, pickle the result variables and save them
        # with a unique name
        out = {
            'identifier': identifier,
            'dataframe': df_resampled,
            'metadata': info,
            'log_content': log_contents,
        }
        with open(
            Path(f'extra/structural_analysis/results/{sub_path}edp_{identifier}'), 'wb'
        ) as f:
            pickle.dump(out, f)


if __name__ == '__main__':
    main()
