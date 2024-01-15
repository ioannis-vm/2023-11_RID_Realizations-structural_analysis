"""
Generates an input file for use with CS_Selection in order to select
ground motions for each hazard level.

"""

import pandas as pd
from src.util import read_study_param

# initialize
dataframe_rows = []

archetype = 'scbf_9_ii'

num_hz = int(read_study_param("extra/structural_analysis/data/study_vars/m"))
vs30 = float(read_study_param("extra/structural_analysis/data/study_vars/vs30"))

t_bar = float(
    read_study_param(f"extra/structural_analysis/data/{archetype}/period_closest")
)
conditioning_period = t_bar

# initialize
dfs_hz = []
for hz in range(num_hz):
    path = (
        f"extra/structural_analysis/results/site_hazard/"
        f"{archetype}/deaggregation_{hz+1}.txt"
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
    df.columns = [f"hz_{hz+1}"]
    dfs_hz.append(df)
df = pd.concat(dfs_hz, axis=1)

df.columns.names = ["hazard_level"]
df = df.T


# store deaggregation results
df.to_csv("extra/structural_analysis/results/site_hazard/deaggregation.csv")

# generate input file for CS_Selection
rows = []
for hz in range(num_hz):
    rows.append(
        [
            conditioning_period,
            df.at[(f"hz_{hz+1}"), "Mbar"],
            df.at[(f"hz_{hz+1}"), "Dbar"],
            df.at[(f"hz_{hz+1}"), "Ebar"],
            vs30,
            f"extra/structural_analysis/results/site_hazard/{archetype}/",
            (
                f"extra/structural_analysis/results/site_hazard/"
                f"{archetype}/required_records_hz_{hz+1}.txt"
            ),
            archetype,
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
    "extra/structural_analysis/results/site_hazard/CS_Selection_input_file.csv"
)
