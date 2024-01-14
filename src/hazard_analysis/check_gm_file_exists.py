"""
Check that all required ground motion files exist
"""

import pandas as pd
from tqdm import tqdm
from osmg.ground_motion_utils import import_PEER
from extra.structural_analysis.src.util import retrieve_peer_gm_data

df = pd.read_csv(
    "extra/structural_analysis/results/site_hazard/ground_motion_group.csv",
    index_col=0,
)

durations = []

for rsn in tqdm(df.index):
    filenames = retrieve_peer_gm_data(rsn)

    # verify that the file exists and can be loaded properly
    for filename in filenames:
        if filename:
            try:
                gm_data = import_PEER(filename)
                durations.append(gm_data[-1, 0])
            except FileNotFoundError as exc:
                raise FileNotFoundError(f"{filename} not found.") from exc

df_dur = pd.DataFrame(durations)
print(df_dur.describe())
