#!/bin/bash

# This script ensures that the files necessary for
# site_gm_selection.py are prersent.

# check if the flatfile is present
filepath=extra/structural_analysis/data/peer_nga_west_2/
zipfile=Updated_NGA_West2_flatfiles_part1.zip
xlsfile=Updated_NGA_West2_Flatfile_RotD50_d050_public_version.xlsx
csvfile=Updated_NGA_West2_Flatfile_RotD50_d050_public_version.csv

# Note: The 5% damped RotD50 spectra are located in the first part of
# the database, so we don't have to download the second part.

if [ -f "$filepath""$csvfile" ]; then
    echo "The file exists."
else
    echo "The file does not exist. Downloading."
    wget --directory-prefix $filepath "https://apps.peer.berkeley.edu/ngawest2/wp-content/uploads/2010/09/Updated_NGA_West2_flatfiles_part1.zip"
    unzip "$filepath""$zipfile" -d $filepath
fi
