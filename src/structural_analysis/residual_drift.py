"""
Determine residual drifts
"""

from itertools import product
import numpy as np
import pandas as pd
from tqdm import tqdm
from src.util import store_info
from extra.structural_analysis.src.util import read_study_param
from extra.structural_analysis.src.util import check_logs


def get_rid(vals):
    """
    Estimate residual drift.
    """
    vdiff = vals.diff()
    vdiffsgn = np.sign(vdiff)
    cdiffsgndiff = np.diff(vdiffsgn)
    downs = np.where(cdiffsgndiff == 2)[0].reshape(-1)
    ups = np.where(cdiffsgndiff == -2)[0].reshape(-1)

    residual_drift = np.abs((vals.iloc[ups[-1]] + vals.iloc[downs[-1]]) / 2.00)

    return residual_drift, ups, downs


# fig, ax = plt.subplots(num_stories+1, 1, sharex=True)
# for i in range(num_stories):
#     vals = data[('ID', f'{i+1}', '1')]
#     ax[i+1].plot(vals, 'k')
#     rid, ups, downs = get_rid(vals)
#     ax[i+1].scatter(vals.index[ups], vals.iloc[ups], color='C0')
#     ax[i+1].scatter(vals.index[downs], vals.iloc[downs], color='C3')
#     ax[i+1].axhline(get_rid(data[('ID', f'{i+1}', '1')])[0], color='k')
#     ax[i+1].grid(which='both', linewidth=0.30)
# ax[0].plot(data[('FA', '0', '1')]/386.22)
# plt.show()


# ---------------------------- #
# gather data for all analyses #
# ---------------------------- #

types = ("scbf",)
stors = ("9",)
rcs = ("ii",)

ngm_cs = int(read_study_param("extra/structural_analysis/data/study_vars/ngm_cs"))
nhz = int(read_study_param("extra/structural_analysis/data/study_vars/m"))

hzs = [f"{i + 1}" for i in range(nhz)]
gms = [f"gm{i + 1}" for i in range(ngm_cs)]

total = len(types) * len(stors) * len(rcs) * len(hzs)
pbar = tqdm(total=total, unit="item")
for tp, st, rc, hz in product(types, stors, rcs, hzs):
    pbar.update(1)

    archetype = f"{tp}_{st}_{rc}"
    summary_df_path = (
        f"extra/structural_analysis/results/{archetype}/edp/{hz}/response.parquet"
    )
    summary_df = pd.read_parquet(summary_df_path)

    num_stories = int(st)

    rid_columns: dict[tuple[str, str, str], list[np.ndarray]] = {}

    for gm in gms:
        for dr in ("x", "y"):
            base_path = (
                f"extra/structural_analysis/results/"
                f"{archetype}/individual_files/{hz}/{gm}"
            )
            response_path = f"{base_path}/results_{dr}.parquet"
            log_path = f"{base_path}/log_{dr}"
            # check if analysis converged witout any issues
            assert check_logs(log_path) == "finished"
            data = pd.read_parquet(response_path)
            data.index = pd.Index(data["time"].to_numpy().reshape(-1))
            for drop_key in ("time", "Rtime", "Subdiv", "Vb"):
                data = data.drop(drop_key, axis=1)
            if dr == "x":
                idr = 1
            else:
                idr = 2
            for i in range(num_stories):
                index = ("RID", f"{i + 1}", f"{idr}")
                vals = data[("ID", f"{i + 1}", f"{idr}")]
                rid, _, _ = get_rid(vals)
                if index in rid_columns:
                    rid_columns[index].append(rid)
                else:
                    rid_columns[index] = [rid]

    rid_df = pd.DataFrame(rid_columns)
    all_df = pd.concat((summary_df, rid_df), axis=1)
    all_df.sort_index(axis=1, inplace=True)
    summary_df_path_updated = store_info(
        f"extra/structural_analysis/results/{archetype}/edp/{hz}/"
        "response_rid.parquet",
        [summary_df_path],
    )
    all_df.to_parquet(summary_df_path_updated)
