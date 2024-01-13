# Reproducing the results

## Set up envrionment

```
# Navigate to the project root directory
$ cd {...}/2023-11_RID_Realizations
# Add it to PYTHONPATH
$ export PYTHONPATH=$PYTHONPATH:$(pwd)
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
