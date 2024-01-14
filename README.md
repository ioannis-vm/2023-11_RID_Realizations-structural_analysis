# Reproducing the results

## Set up envrionment

```
# Navigate to the project root directory
$ cd {...}/2023-11_RID_Realizations
# Add it to PYTHONPATH
$ export PYTHONPATH=$PYTHONPATH:$(pwd)
# Install additional requirements
$ cd extra/structural_analysis
$ python -m pip install -r requirements_extra.txt
```

## Seismic hazard analysis and ground motion selection

```
# Generate all required hazard curves with OpenSHA
$ ./extra/structural_analysis/src/hazard_analysis/site_hazard_curves.sh
# Determine hazard levels for the multi-stripe analysis
$ python ./extra/structural_analysis/src/hazard_analysis/site_hazard.py
# Perofrm seismic hazard deaggregation for each hazard level
$ ./extra/structural_analysis/src/hazard_analysis/site_hazard_deagg.sh
# Generate the input file for CS Selection, used for ground motion selection with CS targets
$ python extra/structural_analysis/src/hazard_analysis/cs_selection_input_file.py
# In Matlab, add the root directory to the path and run
# extra/structural_analysis/src/hazard_analysis/MAIN_select_motions_custom.m
# Then, process the generated output files
$ python extra/structural_analysis/src/hazard_analysis/cs_selection_process_output.py
```
This generates:
`extra/structural_analysis/results/site_hazard/required_records_and_scaling_factors.csv`  
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

Update the scaling factors so that they match with the target UHSs.
```
$ python extra/structural_analysis/src/hazard_analysis/update_scaling_factors.py
```
This generates the concisely named `required_records_and_scaling_factors_adjusted_to_cms.csv`, containing the scaling factors used in the study.
It also generates figures of the ground motion suites and against the target spectra for each hazard level.  
`max_scaling_factor.py` can be used to determine the resulting maximum scaling after the scaling factor modification.  
`check_gm_file_exists.py` can be used to verify that all ground motion files that are needed have been downloaded and can be parsed without any issues.

## Structural analysis

The individual time-history analyses results can be reproduced as follows:
```
$ python extra/structural_analysis/src/structural_analysis/response_2d.py '--archetype' 'scbf_9_ii' '--hazard_level' 'X' '--gm_number' 'Y' '--analysis_dt' '0.01' '--direction' 'Z'
```
where X ranges from 1 to 25, Y from 1 to 40, and Z can be either "x" or "y".

We used HPC to run all the analyses.

