"""
Ground motion selection, using ground motions from the PEER NGA West 2
Database.

"""

from math import ceil
from itertools import product
from tqdm import tqdm
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from src.util import store_info
from extra.structural_analysis.src.util import read_study_param
from extra.structural_analysis.src.util import retrieve_peer_gm_data

# pylint: disable=invalid-name
# flake8: noqa=W605


def read_flatfile() -> pd.DataFrame:
    # read the csv file
    flatfile = (
        "extra/structural_analysis/data/peer_nga_west_2/"
        "Updated_NGA_West2_Flatfile_RotD50"
        "_d050_public_version.xlsx"
    )

    df = pd.read_excel(flatfile, index_col=0)  # takes a while

    return df


def filter_flatfile(
    df: pd.DataFrame,
    rsn_exclude: list[int],
    rsn_specific: list[int],
    limits: pd.DataFrame,
) -> pd.DataFrame:
    # replace na flags with actual nas
    df.replace(-999, np.NaN, inplace=True)
    # some rows contain nan values for the spectra.
    # we exclude those records.
    df = df[df["T0.010S"].notna()]

    for excl in rsn_exclude:
        df.drop(index=excl, inplace=True)

    if rsn_specific:
        df = df.loc[rsn_specific, :]

    # filter records based on attributes
    df = df[df['Earthquake Magnitude'].astype("float") < limits.at['max', 'mw']]
    df = df[df['Earthquake Magnitude'] > limits.at['min', 'mw']]
    df = df[df['EpiD (km)'] < limits.at['max', 'dist']]
    df = df[df['EpiD (km)'] > limits.at['min', 'dist']]
    df = df[df['Vs30 (m/s) selected for analysis'] < limits.at['max', 'vs30']]
    df = df[df['Vs30 (m/s) selected for analysis'] > limits.at['min', 'vs30']]

    return df


def get_periods(df: pd.DataFrame) -> np.ndarray:
    # generate a matrix of all available spectra
    # Note: The PEER flatfile contains spectral values for periods higher
    # than 10s, but we don't use those since our target spectra only go up
    # to 10s.
    periods = df.columns[
        df.columns.get_loc("T0.010S") : df.columns.get_loc("T10.000S") + 1  # type: ignore
    ].to_numpy()
    periods = np.array([float(p.replace('T', '').replace('S', '')) for p in periods])
    return periods


def split_database_pulse_like(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    # separate pulse-like records
    df_pulse = df[~pd.isna(df['Tp'])]
    df_no_pulse = df[pd.isna(df['Tp'])]
    return df_pulse, df_no_pulse


def get_records(filtered_record_df, target_sa, num, periods, limits):
    """
    Selects records
    """
    spectra = filtered_record_df.loc[:, "T0.010S":"T10.000S"].T
    spectra.index = periods
    n_spec = spectra.shape[1]
    if n_spec < num:
        print(spectra)
        raise ValueError(f"df contains fewer records than num={num}")
    df_factors = pd.DataFrame(columns=["scaling", "mse"], index=spectra.columns)

    t = target_sa
    match_periods = np.linspace(periods[0], periods[-1], 10000)
    target_ifun = interp1d(periods, t)

    for col in spectra:
        s = spectra[col].to_numpy()
        spectrum_ifun = interp1d(periods, s)
        w = np.empty(len(match_periods))
        w[match_periods < 0.30] = 1.00
        w[match_periods > 0.30] = 5.00
        w[match_periods > 2.00] = 1.00
        t = target_ifun(match_periods) * w
        s = spectrum_ifun(match_periods) * w
        c = (t.T @ s) / (s.T @ s)
        df_factors.at[col, "scaling"] = c
        df_factors.at[col, "mse"] = np.linalg.norm(t - c * s)
    # scaling factor filter
    df_factors = df_factors[df_factors["scaling"] < limits.at["max", "scaling"]]
    df_factors = df_factors[df_factors["scaling"] > limits.at["min", "scaling"]]
    # order by lowest MSE
    df_factors['Earthquake Name'] = filtered_record_df.loc[
        df_factors.index, 'Earthquake Name'
    ]
    # remove a few rows
    # (1) drop aftershock events
    df_factors = df_factors[
        ~df_factors['Earthquake Name'].str.contains('aftershock')
    ]
    # (2) replace numbered entries of the same earthquake with just
    # the name
    df_factors['Earthquake Name'] = (
        df_factors['Earthquake Name']
        .str.replace(r'-\d+', '', regex=True)
        .replace(r'\(\d+\)', '', regex=True)
    )

    # only keep one record from each event
    # df_factors.drop_duplicates(subset="Earthquake Name", keep='first', inplace=True)
    # keep up to ten records from the same event (instead of removing
    # all duplicates---because we would not have enough ground
    # motions)
    # old line:
    # df_factors.sort_values(by=["Earthquake Name", "mse"], inplace=True)
    for num_duplicate_events in range(1, 21):
        df_partial_deduplication = (
            df_factors.groupby('Earthquake Name').head(num_duplicate_events).copy()
        )  # new line
        df_partial_deduplication.drop(columns='Earthquake Name', inplace=True)
        df_partial_deduplication.sort_values(by=["mse"], inplace=True)
        n_spec = len(df_partial_deduplication)
        if n_spec > num:
            return df_partial_deduplication.iloc[0:num, :]
    raise ValueError(f"df contains fewer records than num={num}")


def find_records(
    archetype: str,
    hazard_level: str,
    pulse_like: bool,
    limits: pd.DataFrame,
    periods: np.ndarray,
    df_pulse: pd.DataFrame,
    num_records_pulse: int,
    df_no_pulse: pd.DataFrame,
    num_records: int,
) -> pd.DataFrame:

    target_spectrum = pd.read_csv(
        (
            f"extra/structural_analysis/results/"
            f"site_hazard/{archetype}/target_mean_{hazard_level}.csv"
        ),
        names=['T', 'Sa'],
        index_col=0,
    )
    target_spectrum['Sa'] = np.exp(target_spectrum['Sa'])
    target_spectrum.loc[0.00, 'Sa'] = target_spectrum.loc[0.10, 'Sa']  # type: ignore
    target_spectrum.sort_index(inplace=True)
    interp_func = interp1d(
        target_spectrum.index.to_numpy(), target_spectrum['Sa'].to_numpy()
    )
    target_sa = interp_func(periods)

    if pulse_like:
        records = get_records(
            df_pulse, target_sa, num_records_pulse, periods, limits
        )
    else:
        records = get_records(df_no_pulse, target_sa, num_records, periods, limits)

    return records


def main():
    # search parameters
    limits = pd.DataFrame(index=('min', 'max'))
    limits['mw'] = (0.00, np.inf)
    limits['dist'] = (0.00, np.inf)
    limits['vs30'] = (0.00, np.inf)
    limits['scaling'] = (0.00, 6.00)

    print('Specified record selection limits')
    print(limits)
    print()

    rsn_specific = tuple()
    rsn_exclude = tuple()

    # get number of records from data/
    num_records = int(
        read_study_param('extra/structural_analysis/data/study_vars/ngm_cms')
    )
    num_records_pulse = int(
        int(read_study_param('extra/structural_analysis/data/study_vars/ngm_cms'))
        / 4.00
    )
    m = int(read_study_param('extra/structural_analysis/data/study_vars/m'))

    # read dataframes (takes some time)
    df = read_flatfile()
    df = filter_flatfile(df, rsn_exclude, rsn_specific, limits)
    periods = get_periods(df)
    df_pulse, df_no_pulse = split_database_pulse_like(df)

    # define cases
    systems = ('smrf', 'scbf', 'brbf')
    stories = ('3', '6', '9')
    rcs = ('ii', 'iv')
    hzs = [f'{i+1}' for i in range(m)]
    pulse_cases = (True, False)

    # select records (takses more time than it should..)
    records_data = {}
    for index in tqdm(list(product(systems, stories, rcs, hzs, pulse_cases))):
        if index in records_data:
            # (in case of continuation of an existing interrupted run)
            continue
        system, story, rc, hz, pulse = index
        records_data[index] = find_records(
            f'{system}_{story}_{rc}',
            hz,
            pulse,
            limits,
            periods,
            df_pulse,
            num_records_pulse,
            df_no_pulse,
            num_records,
        )
    records_df = pd.concat(records_data.values(), keys=records_data.keys())
    records_df.index.names = ['system', 'st', 'rc', 'hz', 'pulse', 'rsn']

    # write the dataframe to a file
    records_df.to_csv(
        store_info(
            'extra/structural_analysis/results/site_hazard/ground_motions_cms.csv'
        )
    )

    # identify unique RSNS
    rsns = records_df.index.get_level_values('rsn').unique().sort_values()

    # check which ones we need to download
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

    # prepare RSN group files for searching
    gm_group = pd.Series(index=required_rsns, dtype="int")
    num_groups = ceil(len(required_rsns) / 100)
    for group in range(num_groups):
        istart = 100 * group
        iend = min(100 + 100 * group, len(required_rsns))
        gm_group[required_rsns[istart:iend]] = group
        with open(
            store_info(
                f"extra/structural_analysis/results/site_hazard/"
                f"rsns_unique_cms_{group+1}.txt"
            ),
            "w",
            encoding="utf-8",
        ) as f:
            f.write(", ".join([f"{r}" for r in required_rsns[istart:iend]]))


if __name__ == '__main__':
    main()
