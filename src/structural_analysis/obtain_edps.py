"""
Read time-history analysis results form databases and extract the
relevant EDPs
"""

import pickle
import pandas as pd
from tqdm import tqdm
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
    edps = dataframe.abs().max().drop(['Rtime', 'Subdiv', 'Vb', 'time'])
    edps['FA'] /= 386.22
    edps.index = pd.MultiIndex.from_tuples(
        [(f'P{x[0]}', x[1], x[2]) for x in edps.index]
    )
    rid = dataframe.iloc[-1, :]['ID'].abs()
    rid.index = pd.MultiIndex.from_tuples([('RID', x[0], x[1]) for x in rid.index])
    edps = pd.concat((edps, rid), axis=0)


def main():
    database_paths = {
        'extra/structural_analysis/results/results.sqlite',
    }

    result_db_handler = DB_Handler(
        db_path='extra/structural_analysis/results/edps.sqlite'
    )
    processed_identifiers = set(result_db_handler.list_identifiers())

    issue = []
    already_processed = []

    for path in database_paths:
        db_handler = DB_Handler(db_path=path)
        identifiers = db_handler.list_identifiers()

        for identifier in tqdm(identifiers):
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
    with open('extra/structural_analysis/results/edps_issue.pickle', 'wb') as f:
        pickle.dump(issue, f)

if __name__ == '__main__':
    main()
