import os
import sqlite3
import glob
from tqdm import tqdm


target_db = 'results.sqlite'

# Connect to the main database
conn = sqlite3.connect(target_db)
cursor = conn.cursor()

# Find all SQLite files in the specified directory with the pattern results_*.sqlite
db_files = glob.glob("results_*.sqlite")

for db_file in tqdm(db_files):
    cursor.execute(f"ATTACH DATABASE '{db_file}' AS toMerge")
    conn.commit()
    cursor.execute("INSERT INTO results_table SELECT * FROM toMerge.results_table")
    conn.commit()
    cursor.execute("DETACH DATABASE toMerge")
    conn.commit()
    os.remove(db_file)

# Close the connection to the main database
conn.close()
