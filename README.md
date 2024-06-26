# Reproducing the results

## Set up environment

```
# Navigate to the project root directory
$ cd {...}/2023-11_RID_Realizations
# Add it to PYTHONPATH
$ export PYTHONPATH=$PYTHONPATH:$(pwd)
# Install additional requirements
$ python -m pip install -r extra/structural_analysis/requirements_extra.txt
```

## Seismic hazard analysis and ground motion selection

```
# Generate all required hazard curves with OpenSHA
$ ./extra/structural_analysis/src/hazard_analysis/site_hazard_curves.sh
# Determine hazard levels for the multi-stripe analysis
$ python ./extra/structural_analysis/src/hazard_analysis/site_hazard.py
# Perform seismic hazard deaggregation for each hazard level
$ ./extra/structural_analysis/src/hazard_analysis/site_hazard_deagg.sh
# Generate the input file for CS Selection, used for ground motion selection with CS targets
$ python extra/structural_analysis/src/hazard_analysis/cs_selection_input_file.py
# In Matlab, add the root directory to the path and run
# extra/structural_analysis/src/hazard_analysis/MAIN_select_motions_custom.m
# Then, process the generated output files
$ python extra/structural_analysis/src/hazard_analysis/cs_selection_process_output.py
```
This generates:
`extra/structural_analysis/results/site_hazard/required_records_and_scaling_factors_cs.csv`  
`extra/structural_analysis/results/site_hazard/ground_motion_group.csv`  
At this point, download ground motions from the PEER database.
The `results/site_hazard/rsns_unique_*.txt` files can be used to limit the RSNs in groups of 100.
Store them in `data/ground_motions` in the following directory format:
```
data/ground_motions/PEERNGARecords_Unscaled(0)/
data/ground_motions/PEERNGARecords_Unscaled(1)/
data/ground_motions/PEERNGARecords_Unscaled(2)/
...
data/ground_motions/PEERNGARecords_Unscaled(n)/
```

Note that MAIN_select_motions_custom.m was ran separately for various groups of hazard levels, since they were modified during the course of the project. The initial execution involved 25 hazard levels. Four hazard levels were later added, aimed at simulating significant shaking to obtain large RID-PID results for RC IV archetypes. `maxScale` was increased to 12.00 for those, and the pool of ground motions to select from was restricted to those already available due to imposed limitations in obtaining more records.

## Structural analysis

The individual time-history analysis results can be reproduced as follows:
```
$ python extra/structural_analysis/src/structural_analysis/response_2d.py '--archetype' 'scbf_9_ii' '--hazard_level' 'X' '--gm_number' 'Y' '--analysis_dt' '0.01' '--direction' 'Z'
```
where X ranges from 1 to 25, Y from 1 to 40, and Z can be either "x" or "y".

We used HPC to run all the analyses.

```
# Gather peak response
$ python extra/structural_analysis/src/structural_analysis/response_vectors.py
# Add RIDs
$ python extra/structural_analysis/src/structural_analysis/residual_drift.py
# Gather EDPs of all hazard levels in one file
$ python extra/structural_analysis/src/structural_analysis/gather_edps.py
# move the resulting file to the main repo
cp extra/structural_analysis/results/edp.parquet data/edp_extra.parquet
```

`review_plot_aggregated_response.py` and `review_plot_response.py` can be used to plot the analysis results.

## DVC

As with the main repo, the `data/`, `figures/` and `results/` directories are tracked with DVC.

After cloning the repository and setting up the environment, issue the following command to pull the files:
```
$ dvc pull
```

(For internal use only)---After making changes, they should be added with DVC and then committed with git.
```

# changes in data/
$ dvc add data

# changes in results/
$ dvc add results

# changes in figures/
$ dvc add figures

$ dvc push
$ git add {changed-dvc-files}
$ git commit -m 'DVC - update results'

```
