"""
Processes the files generated by CS_Selection

"""

from math import ceil
import numpy as np
import pandas as pd
from tqdm import tqdm
from src.util import store_info
from extra.structural_analysis.src.util import read_study_param
from extra.structural_analysis.src.util import retrieve_peer_gm_data

# initialize
dataframe_rows = []

# archetype information
codes = ("smrf", "scbf", "brbf")
stories = ("3", "6", "9")
rcs = ("ii", "iv")
cases = [f"{c}_{s}_{r}" for c in codes for s in stories for r in rcs]

num_hz = int(read_study_param("extra/structural_analysis/data/study_vars/m"))
ngm = int(read_study_param("extra/structural_analysis/data/study_vars/ngm_cs"))

# initialize
dfs_arch = []
conditioning_periods = pd.Series(np.empty(len(cases)), index=cases)

for arch in cases:
    t_bar = float(
        read_study_param(f"extra/structural_analysis/data/{arch}/period_closest")
    )
    conditioning_periods[arch] = t_bar

    # initialize
    dfs_hz = []
    for hz in range(num_hz):
        path = (
            f"extra/structural_analysis/results/site_hazard/"
            f"{arch}/required_records_hz_{hz+1}"
        )
        df = pd.read_csv(path, skiprows=6, sep="	", index_col=0, header=[0])
        df.columns = [x.strip() for x in df.columns]
        df = df.loc[:, ("Record Sequence Number", "Scale Factor")]
        df = df.sort_values(by="Record Sequence Number")
        df.index = range(1, ngm + 1)
        df.index.name = "Record Number"
        df.columns = ["RSN", "SF"]
        dfs_hz.append(df)
    df = pd.concat(dfs_hz, axis=1, keys=[f"hz_{i+1}" for i in range(num_hz)])
    dfs_arch.append(df)

df = pd.concat(dfs_arch, axis=1, keys=cases)
df.columns.names = ["archetype", "hazard_level", "quantity"]
df = df.T

# store deaggregation results for all achetypes in the form of a csv
# file
df.to_csv(
    store_info(
        "extra/structural_analysis/results/site_hazard/"
        "required_records_and_scaling_factors_cs.csv"
    )
)

# obtain unique RSNs to download from the ground motion database
rsns = df.xs("RSN", level=2).astype(int).unstack().unstack().unique()
rsns = pd.Series(rsns).sort_values()
rsns.index = range(len(rsns))
# num_times = (df.xs('RSN', level=2).astype(int)
#              .unstack().unstack().value_counts())


# determine which ones we already have
def get_available_rsn_list() -> tuple[list[int], list[int]]:
    avail_rsns = []
    required_rsns = []
    for rsn in tqdm(rsns):
        try:
            retrieve_peer_gm_data(rsn)
            avail_rsns.append(rsn)
        except ValueError:
            required_rsns.append(rsn)
    return avail_rsns, required_rsns


avail_rsns, required_rsns = get_available_rsn_list()
print(
    f'{float(len(avail_rsns))/float(len(rsns))*100:.0f}% '
    f'of records are available'
)


gm_group = pd.Series(index=required_rsns, dtype="int")
num_groups = ceil(len(required_rsns) / 100)
for group in range(num_groups):
    istart = 100 * group
    iend = min(100 + 100 * group, len(required_rsns))
    gm_group[required_rsns[istart:iend]] = group
    with open(
        store_info(
            f"extra/structural_analysis/results/site_hazard/rsns_unique_{group+1}_2.txt"
        ),
        "w",
        encoding="utf-8",
    ) as f:
        f.write(", ".join([f"{r}" for r in required_rsns[istart:iend]]))
