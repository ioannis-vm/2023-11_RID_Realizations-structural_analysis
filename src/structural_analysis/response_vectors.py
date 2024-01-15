"""
Gather analysis results and form a standard PBEE input file
"""

import pandas as pd
from osmg.common import G_CONST_IMPERIAL
from src.util import store_info
from src.util import read_study_param

# pylint: disable=invalid-name


def failed_to_converge(logfile):
    """
    Determine if the analysis failed based on the contents of a
    logfile
    """
    with open(logfile, "r", encoding="utf-8") as f:
        contents = f.read()
    return bool("Analysis failed to converge" in contents)


def process_item(item):
    """
    Read all the analysis results and gather the peak results
    considering all ground motion scenarios.

    """

    archetype_code, hz_lvl = item

    input_dir = (
        f"extra/structural_analysis/results/{archetype_code}/response_modal/{hz_lvl}"
    )
    output_dir = (
        f"extra/structural_analysis/results/{archetype_code}/edp/{hz_lvl}"
    )

    # determine the number of input files
    # (that should be equal to the number of directories)
    num_inputs = int(
        read_study_param("extra/structural_analysis/data/study_vars/ngm")
    )

    response_dirs = [
        f"{input_dir}/gm{i+1}"
        for input_dir, i in zip([input_dir] * num_inputs, range(num_inputs))
    ]

    dfs = []
    for i, response_dir in enumerate(response_dirs):
        try:
            df_x = (
                pd.read_parquet(f"{response_dir}/results_x.parquet")
                .drop(columns=["time", "Rtime", "Subdiv"])
                .abs()
                .max(axis=0)
            )
            fail_x = failed_to_converge(f"{response_dir}/log_x")
            df_y = (
                pd.read_parquet(f"{response_dir}/results_y.parquet")
                .drop(columns=["time", "Rtime", "Subdiv"])
                .abs()
                .max(axis=0)
            )
            fail_y = failed_to_converge(f"{response_dir}/log_y")
            if (not fail_x) and (not fail_y):
                df = pd.concat((df_x, df_y)).sort_index()
                df["FA"] /= G_CONST_IMPERIAL
                dfs.append(df)
            else:
                print(f"Warning: {input_dir} failed to converge.")
                print(f"{response_dir}")
        except FileNotFoundError:
            print(f"Warning: skipping {input_dir}")
            print(f"{response_dir}")

    df_all = pd.concat(dfs, axis=1).T

    # replace column names to highlight the fact that it's peak values
    df_all.columns = df_all.columns.set_levels(
        "P" + df_all.columns.levels[0], level=0
    )

    df_all.to_parquet(store_info(output_dir + "/response.parquet"))


def main():
    num_hz = int(read_study_param("extra/structural_analysis/data/study_vars/m"))
    for i in range(num_hz):
        process_item(('scbf_9_ii', f'{i+1}'))
