"""
Generates an input file for use with CS_Selection in order to select
ground motions for each archetype and hazard level.

"""

import numpy as np
import pandas as pd
from src.util import store_info
from extra.structural_analysis.src.util import read_study_param


def main() -> None:
    # archetype information
    codes = ("smrf", "scbf", "brbf")
    stories = ("3", "6", "9")
    rcs = ("ii", "iv")
    cases = [f"{c}_{s}_{r}" for c in codes for s in stories for r in rcs]

    num_hz = int(read_study_param("extra/structural_analysis/data/study_vars/m"))
    vs30 = float(read_study_param("extra/structural_analysis/data/study_vars/vs30"))

    dfs_arch = []
    conditioning_periods = pd.Series(np.empty(len(cases)), index=cases)

    for arch in cases:
        t_bar = float(read_study_param(f"extra/structural_analysis/data/{arch}/period_closest"))
        conditioning_periods[arch] = t_bar

        dfs_hz = []
        for hz in range(num_hz):
            path = (
                f"extra/structural_analysis/results/"
                f"site_hazard/{arch}/deaggregation_{hz+1}.txt"
            )
            df = pd.read_csv(
                path,
                skiprows=2,
                skipfooter=4,
                sep=" = ",
                index_col=0,
                engine="python",
                header=None,
            )
            df.index.name = "parameter"
            df.columns = pd.Index([f"hz_{hz+1}"])
            dfs_hz.append(df)
        df = pd.concat(dfs_hz, axis=1)
        dfs_arch.append(df)

    df = pd.concat(dfs_arch, axis=1, keys=cases)
    df.columns.names = ["archetype", "hazard_level"]
    df = df.T

    # store deaggregation results for all achetypes in the form of a csv
    # file
    df.to_csv(
        store_info("extra/structural_analysis/results/site_hazard/deaggregation.csv")
    )

    # generate input file for CS_Selection
    rows = []
    for arch in cases:
        for hz in range(num_hz):
            rows.append(
                [
                    conditioning_periods[arch],
                    df.at[(arch, f"hz_{hz+1}"), "Mbar"],
                    df.at[(arch, f"hz_{hz+1}"), "Dbar"],
                    df.at[(arch, f"hz_{hz+1}"), "Ebar"],
                    vs30,
                    f"extra/structural_analysis/results/site_hazard/{arch}/",
                    f"required_records_hz_{hz+1}.txt",
                    arch,
                ]
            )
    df_css = pd.DataFrame(
        rows,
        columns=[
            "Tcond",
            "M_bar",
            "Rjb",
            "eps_bar",
            "Vs30",
            "outputDir",
            "outputFile",
            "code",
        ],
    )
    df_css.to_csv(
        store_info(
            "extra/structural_analysis/results/site_hazard/CS_Selection_input_file.csv"
        )
    )


if __name__ == '__main__':
    main()
