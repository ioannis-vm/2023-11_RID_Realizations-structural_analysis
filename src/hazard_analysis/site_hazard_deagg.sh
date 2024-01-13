#!/usr/bin/bash

# Perform seismic hazard deaggregation using DisaggregationCalc.java
# and get GMM mean and stdev results using GMMCalc.java

longitude=$(cat extra/structural_analysis/data/study_vars/longitude)
latitude=$(cat extra/structural_analysis/data/study_vars/latitude)
vs30=$(cat extra/structural_analysis/data/study_vars/vs30)

site_hazard_path="extra/structural_analysis/results/site_hazard/"

# compile java code if it has not been compiled already
jar_file_path="extra/structural_analysis/external_tools/opensha-all.jar"
javafile_path="extra/structural_analysis/src/hazard_analysis/DisaggregationCalc.class"
if [ -f "$javafile_path" ]; then
    echo "Already compiled DisaggregationCalc"
else
    echo "Compiling DisaggregationCalc.java"
    javac -classpath $jar_file_path extra/structural_analysis/src/hazard_analysis/DisaggregationCalc.java
fi

    
# Archetype code
code="scbf_9_ii"
mkdir -p "$site_hazard_path""$code"

# Get the period
period=$(cat extra/structural_analysis/data/$code/period_closest)

# Get the hazard level midpoint Sa's
mapes=$(awk -F, '{if (NR!=1) {print $6}}' "$site_hazard_path""Hazard_Curve_Interval_Data.csv")

i=1
j=1
batch_size=10  # Set the desired batch size here

for mape in $mapes
do
    # perform seismic hazard deaggregation
    sa=$(python extra/structural_analysis/src/hazard_analysis/interp_uhs.py --period $period --mape $mape)
    java -classpath $jar_file_path:extra/structural_analysis/src/hazard_analysis DisaggregationCalc $period $latitude $longitude $vs30 $sa "$site_hazard_path""$code"/"deaggregation_$i.txt" &
    i=$(($i+1))
    j=$(($i+1))

    # Check if the batch size is reached, and wait for the background processes to finish
    if [ $j -ge $batch_size ]; then
        wait
        j=1  # Reset the counter for the next batch
    fi
done
