"""
Database interactions for result storage/retrieval
[Mon Apr  1 10:22:16 CDT 2024]

"""

from __future__ import annotations
from typing import Any
import os
import sqlite3
import pickle
import gzip
import pandas as pd


class DB_Handler:
    """
    Database interactions for result storage/retrieval.

    Attributes
    ----------
    db_path : str
        Path to the SQLite database file.
    """

    def __init__(
        self, db_path: str = 'results.db', temp_dir: str | None = None
    ) -> None:
        """
        Constructor for DB_Handler.

        Parameters
        ----------
        db_path : str, optional
            Path to the database file, defaults to 'results.db'.
        temp_dir : str, optional
            Path to the directory for temporary SQLite files, defaults
            to None.
        """
        self.db_path = db_path
        self.temp_dir = temp_dir
        self._initialize_db()

    def store_data(
        self,
        identifier: str,
        dataframe: pd.DataFrame,
        metadata: str,
        log_content: str,
    ) -> None:
        """
        Store data in the database.

        Parameters
        ----------
        identifier : str
            The base identifier for the data to be stored.
        dataframe : pandas.DataFrame
            The dataframe to be stored in the database.
        metadata : dict
            A dictionary of metadata associated with the simulation.
        log_content : str
            Simulation log file content.
        """
        identifier = self._generate_new_identifier(identifier)

        df_bytes = pickle.dumps(dataframe)
        compressed_df_bytes = gzip.compress(df_bytes)
        metadata_bytes = pickle.dumps(metadata)
        compressed_metadata_bytes = gzip.compress(metadata_bytes)
        log_bytes = log_content.encode('utf-8')
        compressed_log_bytes = gzip.compress(log_bytes)

        chunk_size = 0.5 * 1024 * 1024 * 1024  # 0.5 GB in bytes
        chunks = [
            compressed_df_bytes[i : i + int(chunk_size)]
            for i in range(0, len(compressed_df_bytes), int(chunk_size))
        ]

        with self._get_connection() as conn:
            c = conn.cursor()
            for i, chunk in enumerate(chunks):
                c.execute(
                    '''
                    INSERT INTO results_table
                    (id, chunk_id, data, metadata, log) VALUES (?, ?, ?, ?, ?)
                    ''',
                    (
                        identifier,
                        i,
                        chunk,
                        compressed_metadata_bytes if i == 0 else None,
                        compressed_log_bytes if i == 0 else None,
                    ),
                )
            conn.commit()

    def list_identifiers(self) -> list[str]:
        """
        List all unique identifiers in the database.

        Returns
        -------
        list of str
            A list of unique identifiers found in the database.
        """
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT id FROM results_table')
            identifiers = c.fetchall()

        return [item[0] for item in identifiers]

    def dataframe_identifiers(
        self, column_names: list[str] | None = None, delimiter: str = '::'
    ) -> pd.DataFrame:
        """
        Create a dataframe of identifiers split by a delimiter.

        Parameters
        ----------
        delimiter : str, optional
            The delimiter used to split the identifiers, defaults to
            '::'.
        column_names : list of str, optional
            List of column names to apply to the dataframe.

        Returns
        -------
        pandas.DataFrame
            A dataframe with identifiers split into columns.
        """
        identifiers_list = self.list_identifiers()
        identifiers_splitted = [x.split(delimiter) for x in identifiers_list]
        df = pd.DataFrame(identifiers_splitted)
        if column_names:
            if len(column_names) != len(df.columns):
                raise ValueError(
                    f"Incompatible column name size. "
                    f"Provided: {len(column_names)}. "
                    f"Database: {len(df.columns)}"
                )
            df.columns = pd.Index(column_names)
        return df

    def retrieve_data(
        self, identifier: str
    ) -> tuple[pd.DataFrame | None, str | None, str | None]:
        """
        Retrieve data, metadata, and log content for a given
        identifier.

        Parameters
        ----------
        identifier : str
            The identifier for the data to be retrieved.

        Returns
        -------
        tuple
            A tuple containing a pandas.DataFrame, metadata
            dictionary, and log content string.
        """
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute(
                'SELECT data, metadata, log FROM results_table '
                'WHERE id = ? ORDER BY chunk_id',
                (identifier,),
            )
            rows = c.fetchall()

        if rows:
            compressed_df_bytes = b''.join(row[0] for row in rows)
            dataframe = pickle.loads(gzip.decompress(compressed_df_bytes))

            # Assume metadata and log are stored only in the first chunk
            metadata = pickle.loads(gzip.decompress(rows[0][1])) if rows[0][1] else None
            log_content = (
                gzip.decompress(rows[0][2]).decode('utf-8') if rows[0][2] else None
            )

            return dataframe, metadata, log_content
        return None, None, None

    def retrieve_metadata_only(self, identifier: str) -> tuple[str | None, str | None]:
        """
        Retrieve only metadata and log content for a given identifier.

        Parameters
        ----------
        identifier : str
            The identifier for the metadata and log to be retrieved.

        Returns
        -------
        tuple
            A tuple containing a metadata dictionary and log content
            string.
        """
        with self._get_connection() as conn:
            c = conn.cursor()
            # Fetch only the first chunk for the given identifier
            c.execute(
                'SELECT metadata, log FROM results_table '
                'WHERE id = ? AND chunk_id = 0',
                (identifier,),
            )
            row = c.fetchone()

        if row:
            metadata, log = row
            metadata = pickle.loads(gzip.decompress(metadata)) if metadata else None
            log_content = gzip.decompress(log).decode('utf-8') if log else None

            return metadata, log_content

        return None, None

    def retrieve_metadata_only_bulk(self, identifiers: list[str]) -> dict:
        """
        Retrieve only metadata and log content for a given list of
        identifiers using a single database query.

        Parameters
        ----------
        identifiers : list of str
            A list of identifiers for the metadata and logs to be
            retrieved. The length of the list should be less than
            1000.

        Returns
        -------
        dict
            A dictionary with identifiers as keys and tuples of
            metadata and log content as values.
        """
        results: dict[str, tuple[Any, str | None]] = {}
        if not identifiers:
            return results

        # Use a tuple of identifiers to use the IN clause in SQL query
        identifiers_tuple = tuple(identifiers)

        with self._get_connection() as conn:
            c = conn.cursor()
            # The SQL query uses the IN clause to fetch all relevant entries at once
            query = (
                f"SELECT id, metadata, log FROM results_table "
                f"WHERE id IN ({','.join('?' * len(identifiers))}) "
                f"AND chunk_id = 0"
            )
            c.execute(query, identifiers_tuple)
            rows = c.fetchall()

            for row in rows:
                identifier, metadata, log = row
                metadata = pickle.loads(gzip.decompress(metadata)) if metadata else None
                log_content = gzip.decompress(log).decode('utf-8') if log else None
                results[identifier] = (metadata, log_content)

        return results

    def delete_record(self, identifier: str) -> None:
        """
        Delete a record from the database based on identifier.

        Parameters
        ----------
        identifier : str
            The identifier of the record to be deleted.
        """
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('DELETE FROM results_table WHERE id = ?', (identifier,))
            conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """
        Establish and return a new database connection.

        Returns
        -------
        sqlite3.Connection
            A connection object to the SQLite database.
        """
        if self.temp_dir:
            if not os.path.isdir(self.temp_dir):
                raise ValueError(f'`temp_dir` {self.temp_dir} does not exist.')
            # Set the environment variable for the temporary directory
            os.environ['SQLITE_TMPDIR'] = self.temp_dir

        conn = sqlite3.connect(self.db_path)
        conn.execute('PRAGMA busy_timeout = 600000')  # Set timeout to 10 minutes
        return conn

    def _initialize_db(self) -> None:
        """
        Initialize the database by creating necessary tables.

        """
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute(
                '''
                CREATE TABLE IF NOT EXISTS results_table (
                    id TEXT,
                    chunk_id INTEGER,
                    data BLOB,
                    metadata BLOB,
                    log BLOB,
                    PRIMARY KEY (id, chunk_id)
                )
               '''
            )
            conn.commit()

    def _generate_new_identifier(self, identifier: str) -> str:
        """
        Generate a new unique identifier based on the provided base
        identifier.

        Parameters
        ----------
        identifier : str
            The base identifier to be used for generating a new unique
            identifier.

        Returns
        -------
        str
            A new unique identifier derived from the base identifier.
        """
        with self._get_connection() as conn:
            c = conn.cursor()
            # Fetch all identifiers starting with the base identifier
            pattern = f'{identifier}%'
            c.execute(
                'SELECT id FROM results_table WHERE id LIKE ? ORDER BY id',
                (pattern,),
            )
            existing_ids = [row[0] for row in c.fetchall()]

        # Determine the next unique identifier
        if identifier in existing_ids:
            numbers = [
                int(id_.split('_')[-1])
                for id_ in existing_ids
                if id_.startswith(f'{identifier}_') and id_.split('_')[-1].isdigit()
            ]
            next_number = max(numbers) + 1 if numbers else 1
            new_identifier = f'{identifier}_{next_number}'
        else:
            new_identifier = identifier

        return new_identifier
