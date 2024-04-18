# Why we use branches

`main` is our primary branch with the most up-to-date code.
However, on certain occasions we want to preserve code we wrote that is not needed for reproducing our results, but was relevant at the time it was written.
This is typically the case for tangential code used for quality control or for organization and management of the project's files.
By storing this code in branches we manage to preserve it in a state where it can be revisited and ran, without having to keep updating it every time a breaking change is made in `main`.


# Description of branches

## Operational/management

### 2024-04-migrate_results_to_db
We were initially relying on individual files to store the results of each simulation run.
This is not a good HPC practice as it burdens the file system.
It is advised that users avoid creating thousands of files and instead collect their results on fewer large files.
To address this issue and enhance performance we began utilizing an SQLite database to store our analyses results.
We introduced a convenience class, `DB_Handler` to interact with the database.
We already had existing analysis results stored in individual files[^1] and had to write code to migrate those files into the database.
This branch stores the code used to perform this operation.

### 2024-04_result_gathering_and_cleanup
Some HPC jobs timed out and we had to reschedule certain cases.
This required inspecting the produced results and generating new SLURM files.
This branch stores the relevant code for this operation.

## Quality assurance

### 2024-04_chosing_dt
When doing nonlinear time-history analysis, the time step `dt` needs to be carefully chosen so that we don't waste resources and time but also converge to the right result.
This branch tests that our chosen `dt` meets that goal.
