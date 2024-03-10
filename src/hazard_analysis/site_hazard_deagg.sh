#!/usr/bin/bash

# Perform seismic hazard deaggregation using DisaggregationCalc.java
# and get GMM mean and stdev results using GMMCalc.java

longitude=$(cat extra/structural_analysis/data/study_vars/longitude)
latitude=$(cat extra/structural_analysis/data/study_vars/latitude)
vs30=$(cat extra/structural_analysis/data/study_vars/vs30)


site_hazard_path="extra/structural_analysis/results/site_hazard/"

# get the codes of the archetypes of this study
arch_codes="smrf_3_ii smrf_3_iv smrf_6_ii smrf_6_iv smrf_9_ii smrf_9_iv scbf_3_ii scbf_3_iv scbf_6_ii scbf_6_iv scbf_9_ii scbf_9_iv brbf_3_ii brbf_3_iv brbf_6_ii brbf_6_iv brbf_9_ii brbf_9_iv"

# download the .jar file (if it is not there)
jar_file_path="extra/structural_analysis/external_tools/opensha-all.jar"
if [ -f "$jar_file_path" ]; then
    echo "The file exists."
else
    echo "The file does not exist. Downloading file."
    wget -P external_tools/ "http://opensha.usc.edu/apps/opensha/nightlies/latest/opensha-all.jar"
fi

# compile java code if it has not been compiled already
javafile_path="extra/structural_analysis/src/hazard_analysis/DisaggregationCalc.class"
if [ -f "$javafile_path" ]; then
    echo "Already compiled DisaggregationCalc"
else
    echo "Compiling DisaggregationCalc.java"
    javac -classpath $jar_file_path extra/structural_analysis/src/hazard_analysis/DisaggregationCalc.java
fi

for code in $arch_codes
do
    
    # Get the period of that archetype
    period=$(cat extra/structural_analysis/data/$code/period_closest)

    # Get the hazard level midpoint Sa's
    mapes=$(awk -F, '{if (NR!=1) {print $6}}' extra/structural_analysis/results/site_hazard/Hazard_Curve_Interval_Data.csv)

    i=1
    for mape in $mapes
    do

	# perform seismic hazard deaggregation
	mkdir -p extra/structural_analysis/results/$code/site_hazard
	sa=$(python extra/structural_analysis/src/hazard_analysis/interp_uhs.py --period $period --mape $mape)
	java -classpath $jar_file_path:extra/structural_analysis/src/hazard_analysis DisaggregationCalc $period $latitude $longitude $vs30 $sa extra/structural_analysis/results/site_hazard/$code/deaggregation_$i.txt

	i=$(($i+1))	

    done
        
done
