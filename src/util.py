"""
Utility functions
"""

import os
from io import StringIO
from glob2 import glob
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d


def retrieve_peer_gm_data(rsn, out_type="filenames"):
    """
    Searches all available `_SearchResults.csv` for a given RSN,
    identifies the right folder and retrieves the unscaled RotD50
    response spectrum or the ground motion filenames.

    """

    def get_gm_data(search_results_file):
        """
        Helper function that reads certain contents from a PEER
        `_SearchResults.csv` file.

        """
        with open(search_results_file, "r", encoding="utf-8") as f:
            contents = f.read()

        contents = contents.split(" -- Summary of Metadata of Selected Records --")[
            1
        ].split("\n\n")[0]
        data = StringIO(contents)

        df = pd.read_csv(data, index_col=2)

        return df

    # Find all `_SearchResults.csv` files
    files = glob(
        'extra/structural_analysis/data/ground_motions/*/*/_SearchResults.csv'
    )

    # Identify the one containing the specified `rsn`
    identified_file = None
    for file_path in files:
        data = get_gm_data(file_path)
        if rsn in data.index:
            identified_file = file_path
            break

    if not identified_file:
        raise ValueError(f"rsn not found: {rsn}")

    rootdir = os.path.dirname(identified_file)

    if out_type == "filenames":
        df = get_gm_data(identified_file)

        filenames = df.loc[
            rsn,
            [
                " Horizontal-1 Acc. Filename",
                " Horizontal-2 Acc. Filename",
                " Vertical Acc. Filename",
            ],
        ].to_list()

        result = []
        for filename in filenames:
            if "---" in filename:
                result.append(None)
            else:
                result.append(f"{rootdir}/" + filename.strip())

        return result

    if out_type == "spectrum":
        contents = contents.split(" -- Scaled Spectra used in Search & Scaling --")[
            1
        ].split("\n\n")[0]
        data = StringIO(contents)

        df = pd.read_csv(data, index_col=0)
        # drop stats columns
        df = df.drop(
            columns=[
                "Arithmetic Mean pSa (g)",
                "Arithmetic Mean + Sigma pSa (g)",
                "Arithmetic Mean - Sigma pSa (g)",
            ]
        )
        df.columns = [x.split(" ")[0].split("-")[1] for x in df.columns]
        df.columns.name = "RSN"
        df.columns = df.columns.astype(int)
        df.index.name = "T"

        return df[rsn]

    raise ValueError("Unsupported out_type: {out_type}")


def retrieve_peer_gm_spectra(rsns):
    """
    Uses retrieve_peer_gm_data to prepare a dataframe with response
    spectra for the given RSNs
    """

    rsn_dfs = []
    for rsn in rsns:
        rsn_df = retrieve_peer_gm_data(rsn, out_type="spectrum")
        rsn_dfs.append(rsn_df)
    df = pd.concat(rsn_dfs, keys=rsns, axis=1)

    return df


def interpolate_pd_series(series, values):
    """
    Interpolates a pandas series for specified index values.
    """
    idx_vec = series.index.to_numpy()
    vals_vec = series.to_numpy()
    ifun = interp1d(idx_vec, vals_vec)
    if isinstance(values, float):
        return float(ifun(values))
    if isinstance(values, np.ndarray):
        return ifun(values)
    return ValueError(f"Invalid datatype: {type(values)}")


def file_exists(file_path):
    """
    Checks if a file exists at the specified file path.

    Args:
        file_path (str): The path to the file.

    Returns:
        bool: True if the file exists, False otherwise.
    """
    return os.path.exists(file_path) and os.path.isfile(file_path)


def check_last_line(file_path, target_string):
    """
    Checks if the last line of a file contains a specific string.

    Args:
        file_path (str): The path to the file.
        target_string (str): The string to search for in the last line.

    Returns:
        bool: True if the last line contains the target string, False otherwise.
    """
    with open(file_path, "r", encoding="utf-8") as file:
        lines = file.readlines()

    # Check if the file is not empty
    if lines:
        last_line = lines[-1].strip()  # Remove leading/trailing whitespace

        # Check if the last line contains the target string
        if target_string in last_line:
            return True

    return False


def check_any_line(file_path, target_string):
    """
    Checks if any line of a file contains a specific string.

    Args:
        file_path (str): The path to the file.
        target_string (str): The string to search for in the last line.

    Returns:
        bool: True if the last line contains the target string, False otherwise.
    """
    with open(file_path, "r", encoding="utf-8") as file:
        all_contents = file.read()

    # Check if the file is not empty
    if all_contents:
        if target_string in all_contents:
            return True

    return False


def get_any_line(file_path, target_string):
    """
    Checks if any line of a file contains a specific string.
    If it does, it returns that line.

    Args:
        file_path (str): The path to the file.
        target_string (str): The string to search for in the last line.

    Returns:
        str: The line
    """
    with open(file_path, "r", encoding="utf-8") as file:
        all_contents = file.readlines()

    # Check if the file is not empty
    if all_contents:
        for line in all_contents:
            if target_string in line:
                return line

    return None


def check_logs(path):
    """
    Check the logs of a nonlinear analysis
    """

    exists = os.path.exists(path) and os.path.isfile(path)
    if not exists:
        return "does not exist"
    inter = check_any_line(path, "Analysis interrupted")
    if inter:
        return "interrupted"
    fail = check_any_line(path, "Analysis failed to converge")
    if fail:
        return "failed"
    return "finished"


def read_study_param(param_path):
    """
    Read a study parameter from a file.
    """
    with open(param_path, "r", encoding="utf-8") as f:
        data = f.read()
    return data
