"""
Collects individual result files from results/ and puts them in the
database.
"""

from __future__ import annotations
import os
import pickle
from tqdm import tqdm
from tqdm import trange
import pandas as pd
from extra.structural_analysis.src.db import DB_Handler


def collect() -> None:
    individual_results: list[str] = []
    # added: list[str] = []  # read from pickle instead
    for identifier in os.listdir('extra/structural_analysis/results/'):
        if '::' not in identifier:
            continue
        individual_results.append(identifier)

    db_handler = DB_Handler(db_path='extra/structural_analysis/results/results.sqlite')
    existing = db_handler.list_identifiers()

    for identifier in tqdm(individual_results):
        if identifier in existing:
            continue
        with open(f'extra/structural_analysis/results/{identifier}', 'rb') as f:
            out = pickle.load(f)
            record_id = out['identifier']
            df = out['dataframe']
            info = out['metadata']
            log_contents = out['log_content']

        db_handler.store_data(
            identifier=record_id,
            dataframe=df,
            metadata=info,
            log_content=log_contents,
        )
        assert record_id == identifier


def remove_result_files():
    db_handler = DB_Handler(db_path='extra/structural_analysis/results/results.sqlite')
    existing = db_handler.list_identifiers()
    set_existing = set(existing)

    individual_results = [
        f for f in os.listdir('extra/structural_analysis/results/') if '::' in f
    ]
    db_handler = DB_Handler(db_path='extra/structural_analysis/results/results.sqlite')

    for individual_result in tqdm(individual_results):
        assert individual_result in set_existing
        with open(f'extra/structural_analysis/results/{individual_result}', 'rb') as f:
            data = pickle.load(f)
            record_id = data['identifier']
            assert record_id == individual_result
            df = data['dataframe']
            info = data['metadata']
            log_contents = data['log_content']
        df2, info2, log_contents2 = db_handler.retrieve_data(individual_result)
        pd.testing.assert_frame_equal(df, df2)
        assert info == info2
        assert log_contents == log_contents2
        os.remove(f'extra/structural_analysis/results/{individual_result}')


def remove_failed_from_db():
    db_handler = DB_Handler(
        db_path='extra/structural_analysis/results/results_1.sqlite'
    )
    # db_handler = DB_Handler(
    #     db_path='extra/structural_analysis/results/results_1.sqlite'
    # )
    identifiers = db_handler.list_identifiers()
    with open('remove_failed_from_db_1.pickle', 'rb') as f:
        dct = pickle.load(f)
    valid = dct['valid']
    invalid = dct['invalid']
    processed_chunks = dct['processed']
    chunk_size = 999
    num_chunks = int(len(identifiers) / chunk_size + 0.50)
    for chunk_id in trange(num_chunks):
        if chunk_id in processed_chunks:
            continue
        istart = chunk_id * chunk_size
        iend = chunk_size * (chunk_id + 1)
        if iend > len(identifiers) - 1:
            iend = len(identifiers)
        results = db_handler.retrieve_metadata_only_bulk(identifiers[istart:iend])
        for identifier in identifiers[istart:iend]:
            if (identifier in valid) or (identifier in invalid):
                continue
            info, log = results[identifier]
            log_lines = log.split('\n')[:-1]
            if (
                'Analysis started' in log_lines[0]
                and 'Analysis finished' in log_lines[-1]
                and 'Analysis failed to converge' not in log
                and 'Analysis interrupted' not in log
            ):
                valid.append(identifier)
            else:
                invalid.append(identifier)
        print(f'Invalid size: {len(invalid)}')
        processed_chunks.append(chunk_id)
    with open('remove_failed_from_db_1.pickle', 'wb') as f:
        pickle.dump(
            {
                'valid': valid,
                'invalid': invalid,
                'processed': processed_chunks,
            },
            f,
        )

    # inspect invalid
    # from pprint import pprint
    # pprint(invalid)
    # ['scbf_6_ii::cms::False::13::149::0.001::x::False::modal',
    #  'scbf_6_ii::cs::False::25::10::0.001::x::False::modal',
    #  'scbf_9_ii::cms::True::25::6::0.001::y::False::modal',
    #  'scbf_9_iv::cms::True::14::23::0.001::y::False::modal']
    identifier = 'scbf_9_iv::cms::True::14::23::0.001::y::False::modal'
    df, info, log = db_handler.retrieve_data(identifier)
    # note: all of these cases just failed to converge.

    # removing
    # idents = db_handler.list_identifiers()
    # len(idents)
    # invalid[0] in idents
    # db_handler.delete_record(invalid[0])
    # idents_after = db_handler.list_identifiers()
    # invalid[0] in idents_after
    # len(idents_after)
    for identifier in tqdm(invalid[1:]):
        db_handler.delete_record(identifier)

    # check for duplicate results
    # import re
    # identifiers = db_handler.list_identifiers()
    # pattern = r"_[0-9]+$"
    # duplicate_record_identifiers = [
    #     item[0] for item in identifiers if re.search(pattern, item[0])
    # ]

    # combine databases
    # note: this operation fails on TACC.
    db_handler = DB_Handler(
        db_path='extra/structural_analysis/results/results.sqlite',
        temp_dir='extra/structural_analysis/temp/',
    )
    db_handler.merge_database('extra/structural_analysis/results/results_1.sqlite')


if __name__ == '__main__':
    remove_failed_from_db()
