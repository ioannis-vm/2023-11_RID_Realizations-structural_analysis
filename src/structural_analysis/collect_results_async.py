"""
Collects individual result files from results/ and puts them in the
database.
"""

import os
import pickle
import asyncio
import aiofiles
from tqdm import tqdm
from extra.structural_analysis.src.db import DB_Handler


async def load_pickle_file(path: str):
    async with aiofiles.open(path, 'rb') as f:
        data = await f.read()
    return pickle.loads(data)


async def get_and_store_data(identifier, db_handler, existing, progress_bar, semaphore):
    async with semaphore:
        if identifier in existing:
            progress_bar.update(1)
            return
        out = await load_pickle_file(f'extra/structural_analysis/results/{identifier}')
        record_id = out['identifier']
        assert record_id == identifier
        df = out['dataframe']
        info = out['metadata']
        log_contents = out['log_content']
        db_handler.store_data(
            identifier=record_id,
            dataframe=df,
            metadata=info,
            log_content=log_contents,
        )
        progress_bar.update(1)


async def main():
    db_handler = DB_Handler(db_path='extra/structural_analysis/results/results.sqlite')
    existing = db_handler.list_identifiers()

    individual_results = [
        f for f in os.listdir('extra/structural_analysis/results/') if '::' in f
    ]

    progress_bar = tqdm(total=len(individual_results))

    semaphore = asyncio.Semaphore(10000)

    tasks = [
        get_and_store_data(identifier, db_handler, existing, progress_bar, semaphore)
        for identifier in individual_results
    ]
    await asyncio.gather(*tasks)

    progress_bar.close()


if __name__ == '__main__':
    asyncio.run(main())
