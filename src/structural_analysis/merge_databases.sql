-- Merges a database into another.

-- List tables
-- `.tables`

-- Show the schema for a specific table
-- `.schema table_name`

-- Exit: `.exit`

-- Attach the second database as 'toMerge'
ATTACH DATABASE 'results_XYZ.sqlite' AS toMerge;

-- Start a transaction
BEGIN;

-- Assuming 'TableName' is a table in both databases, insert data from
-- the attached database into the main database
INSERT INTO TableName SELECT * FROM toMerge.TableName;

-- Commit the transaction to finalize the changes
COMMIT;

-- Detach the second database
DETACH DATABASE toMerge;

-- To execute
-- `sqlite3 database.sqlite`
-- then run the commands interactively, or
-- `sqlite3 database.sqlite < commands.sql`
