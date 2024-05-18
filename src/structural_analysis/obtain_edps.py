"""
Read time-history analysis results form databases and extract the
relevant EDPs
"""

import os
import sys
import pickle
import pandas as pd
from extra.structural_analysis.src.db import DB_Handler


def status_from_log(logfile: str) -> str:
    """
    Parse a logfile and determine the analysis status.
    """

    if 'Error' in logfile:
        return 'error'
    if 'Analysis interrupted' in logfile:
        return 'interrupted'
    if 'Analysis failed to converge' in logfile:
        return 'failed to converge'
    if 'Analysis finished' in logfile:
        return 'finished'
    return 'unknown'


def obtain_edps(dataframe):
    """
    Extracts the EDPs from a dataframe containing the full
    time-history analysis results.
    The EDPs are `PFA`, `PFV`, `PID`, and `RID`.

    Parameters
    ----------
    dataframe: pd.DataFrame
        Dataframe containing the full time-hisotyr analysis results.

    Returns
    -------
    pd.DataFrame
        Dataframe containing the EDPs

    """
    edps = dataframe.abs().max().drop(['Rtime', 'Subdiv', 'Vb'])
    edps['FA'] /= 386.22
    edps.index = pd.MultiIndex.from_tuples(
        [(f'P{x[0]}', x[1], x[2]) for x in edps.index]
    )
    rid = dataframe.iloc[-1, :]['ID'].abs()
    rid.index = pd.MultiIndex.from_tuples([('RID', x[0], x[1]) for x in rid.index])
    edps = pd.concat((edps, rid), axis=0)
    return edps


def main():

    i = int(sys.argv[1])
    # i ranges from 0 to 4 (5 values)

    issue_dict_path = 'extra/structural_analysis/results/edps_issue.pickle'
    if not os.path.isfile(issue_dict_path):
        issue = []
        with open(issue_dict_path, 'wb') as f:
            pickle.dump(issue, f)
    else:
        with open(issue_dict_path, 'rb') as f:
            issue = pickle.load(f)

    database_paths = [
        'extra/structural_analysis/results/results_01.sqlite',
        'extra/structural_analysis/results/results_02.sqlite',
        'extra/structural_analysis/results/results_03.sqlite',
        'extra/structural_analysis/results/results_04.sqlite',
        'extra/structural_analysis/results/results_05.sqlite',
        'extra/structural_analysis/results/results_1.sqlite',
        'extra/structural_analysis/results/results_2.sqlite',
        'extra/structural_analysis/results/results_3.sqlite',
        'extra/structural_analysis/results/results_4.sqlite',
        'extra/structural_analysis/results/results_5.sqlite',
        'extra/structural_analysis/results/results_6.sqlite',
        'extra/structural_analysis/results/results_7.sqlite',
        'extra/structural_analysis/results/results_8.sqlite',
        'extra/structural_analysis/results/results_9.sqlite',
        'extra/structural_analysis/results/results_10.sqlite',
    ][i*3:i*3+3]
    
    result_db_handler = DB_Handler(
        db_path='extra/structural_analysis/results/edps.sqlite'
    )
    processed_identifiers = set(result_db_handler.list_identifiers())

    already_processed = []

    for i, path in enumerate(database_paths):
        print(f'Processing path {i + 1} out of {len(database_paths)}.', flush=True)
        db_handler = DB_Handler(db_path=path)
        identifiers = db_handler.list_identifiers()

        for j, identifier in enumerate(identifiers):
            if identifier in processed_identifiers:
                already_processed.append(identifier)
                continue
            dataframe, metadata, log_content = db_handler.retrieve_data(identifier)
            status = status_from_log(log_content)
            if status == 'finished':
                edps = obtain_edps(dataframe)
                result_db_handler.store_data(identifier, edps, '', '')
            else:
                issue.append((status, identifier))
                db_handler.delete_record(identifier)

    with open(issue_dict_path, 'wb') as f:
        pickle.dump(issue, f)


if __name__ == '__main__':
    main()
