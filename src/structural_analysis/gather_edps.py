"""
Extract EDPs from sqlite database and store them in parquet files
"""

from tqdm import tqdm
import pandas as pd
from extra.structural_analysis.src.db import DB_Handler


def parse_id(identifier):
    parts = identifier.split('::')
    (
        archetype,
        suite_type,
        pulse,
        hazard_level,
        ground_motion,
        dt,
        direction,
        progress_bar,
        damping,
    ) = parts
    system, stories, rc = archetype.split('_')
    if pulse == 'True':
        suite_type = 'cs_pulse'
    pbar = bool(progress_bar == 'True')
    return (
        system,
        stories,
        rc,
        suite_type,
        hazard_level,
        ground_motion,
        dt,
        direction,
        pbar,
        damping,
    )


def main():
    db_handler = DB_Handler(db_path='extra/structural_analysis/results/edps.sqlite')
    identifiers = db_handler.list_identifiers()

    # # Remove repeated results
    # repeats = {}
    # for identifier in tqdm(identifiers):
    #     if identifier[-2] == '_':
    #         if identifier[:-2] not in repeats:
    #             repeats[identifier[:-2]] = [identifier]
    #         else:
    #             repeats[identifier[:-2]].append(identifier)

    # for rep in tqdm(repeats):
    #     df, _, _ = db_handler.retrieve_data(rep)
    #     for rrep in repeats[rep]:
    #         ddf, _, _ = db_handler.retrieve_data(rep)
    #         if np.all(ddf == df):
    #             db_handler.delete_record(rrep)
    # # Note: Check for repeated results once again.

    # dts = {}
    # for identifier in tqdm(identifiers):
    #     (
    #         archetype,
    #         suite_type,
    #         hazard_level,
    #         ground_motion,
    #         dt,
    #         direction,
    #         progress_bar,
    #         damping,
    #     ) = parse_id(identifier)
    #     if dt not in dts:
    #         dts[dt] = 1
    #     else:
    #         dts[dt] += 1

    dfs = {}
    for identifier in tqdm(identifiers):
        (
            system,
            stories,
            risk_category,
            suite_type,
            hazard_level,
            ground_motion,
            _,
            direction,
            _,
            _,
        ) = parse_id(identifier)
        df, _, _ = db_handler.retrieve_data(identifier)
        key = (
            system,
            stories,
            risk_category,
            hazard_level,
            ground_motion,
            direction,
        )
        if suite_type in dfs:
            dfs[suite_type][key] = df
        else:
            dfs[suite_type] = {key: df}

    merged_dfs = {}
    for suite_type in dfs:
        if suite_type in merged_dfs:
            continue
        merged_dfs[suite_type] = pd.concat(
            dfs[suite_type].values(), keys=dfs[suite_type].keys()
        )
        merged_dfs[suite_type].index.names = [
            'system',
            'stories',
            'rc',
            'hz',
            'gm',
            'dir',
            'edp',
            'loc',
            'dir_num',
        ]
        merged_dfs[suite_type].index = merged_dfs[suite_type].index.droplevel(
            'dir_num'
        )
        merged_dfs[suite_type].index = merged_dfs[suite_type].index.reorder_levels(
            ['system', 'stories', 'rc', 'hz', 'edp', 'loc', 'dir', 'gm']
        )
    for suite_type in dfs:
        merged_dfs[suite_type] = pd.DataFrame(
            merged_dfs[suite_type], columns=['value']
        )

    for suite_type in dfs:
        merged_dfs[suite_type].to_parquet(f'data/edp_extended_{suite_type}.parquet')


if __name__ == '__main__':
    main()
