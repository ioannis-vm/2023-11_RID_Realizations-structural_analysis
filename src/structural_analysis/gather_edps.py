"""
Determine residual drifts
"""

from itertools import product
import pandas as pd
from tqdm import tqdm
from src.util import read_study_param
from src.util import store_info


def main():
    types = ("scbf",)
    stors = ("9",)
    rcs = ("ii",)

    nhz = int(read_study_param("extra/structural_analysis/data/study_vars/m"))
    hzs = [f"{i+1}" for i in range(nhz)]

    keys = []
    dfs = []

    total = len(types) * len(stors) * len(rcs) * len(hzs)
    pbar = tqdm(total=total, unit="item")
    for tp, st, rc, hz in product(types, stors, rcs, hzs):
        pbar.update(1)

        archetype = f"{tp}_{st}_{rc}"

        summary_df_path_updated = (
            f"extra/structural_analysis/results/"
            f"{archetype}/edp/{hz}/response_rid.parquet"
        )

        df = pd.read_parquet(summary_df_path_updated)
        keys.append((tp, st, rc, hz))
        dfs.append(df)

    pbar.close()

    df = pd.concat(dfs, axis=1, keys=keys)
    df.index.names = ('gm',)
    df.columns.names = ('system', 'stories', 'rc', 'hz', 'edp', 'loc', 'dir')
    df = pd.DataFrame(df.T.stack(), columns=['value'])
    df.to_parquet(store_info('extra/structural_analysis/results/edp.parquet'))


if __name__ == '__main__':
    main()
