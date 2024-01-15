"""
This file is used by `site_hazard_deagg.sh` to interpoalte a hazard
curve and obtain the Sa value at a given MAPE
"""

import argparse
import pandas as pd
from extra.structural_analysis.src.util import interpolate_pd_series

# use: python -m src.hazard_analysis.interp_uhs --period 0.75 --mape 1e-1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--period")
    parser.add_argument("--mape")

    args = parser.parse_args()
    period = float(args.period)
    mape = float(args.mape)

    # load hazard curve
    df = pd.read_csv(
        "extra/structural_analysis/results/site_hazard/hazard_curves.csv",
        index_col=0,
        header=[0, 1],
    )
    new_cols = []
    for col in df.columns:
        new_cols.append((float(col[0]), col[1]))
    df.columns = pd.MultiIndex.from_tuples(new_cols)
    hz_curv = df[(period, "MAPE")]
    hz_curv_inv = pd.Series(hz_curv.index.to_numpy(), index=hz_curv.to_numpy())
    hz_curv_inv.index.name = "MAPE"
    hz_curv_inv.name = period

    sa_val = interpolate_pd_series(hz_curv_inv, mape)
    print(sa_val)


if __name__ == '__main__':
    main()
