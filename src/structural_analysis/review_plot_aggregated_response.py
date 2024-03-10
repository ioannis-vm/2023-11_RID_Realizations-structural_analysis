"""
Plots the aggregated EDPs
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from extra.structural_analysis.src.util import read_study_param

# parameters
archetype = 'scbf_9_ii'
fig_type = 'PID'  # 'PID', 'PFA', 'PFV', 'RID'

num_hz = int(read_study_param("extra/structural_analysis/data/study_vars/m"))
num_gm_cs = int(read_study_param("extra/structural_analysis/data/study_vars/ngm_cs"))

hzs = list(range(4, num_hz, 5))

# axis limits
if fig_type in ["PID", "RID"]:
    xmin = -0.02
    xmax = 0.12
elif fig_type == "PFV":
    xmin = -20
    xmax = 200.00
elif fig_type == "PFA":
    xmin = -0.20
    xmax = 5.90
else:
    raise ValueError(f"Invalid fig_type: {fig_type}")

# read aggregated response into a dataframe
plt.close()
fig, axs = plt.subplots(1, len(hzs), sharex=True, sharey=True, figsize=(10, 6))

col = -1
for ihz in hzs:
    col += 1
    hz = f"{ihz+1}"
    ax = axs[col]
    ax.grid(which="both")

    response_path = (
        f"extra/structural_analysis/results/"
        f"{archetype}/edp/{hz}/response_rid.parquet"
    )

    # load the data, remove the rows corresponding to failed analyses, and
    # drop the `failed` column
    df = pd.read_parquet(response_path)

    num_stories = int(archetype.split("_")[1])

    bar_distance = 0.30
    box_width = 0.08

    pid_df = df[f"{fig_type}"]

    data = pid_df.to_numpy()

    if fig_type in {"FA", "FV"}:
        positions = [-bar_distance / 2.00, +bar_distance / 2.00]
        yticks = [0]
        labels = ["ground"]
        index_shift = -1
    else:
        positions = []
        yticks = []
        labels = []
        index_shift = 0

    for i in range(num_stories):
        i_story = i + 1
        labels.append(f"story {i_story}")
        positions.append(i_story - bar_distance / 2.00)
        positions.append(i_story + bar_distance / 2.00)
        yticks.append(i_story)

    # # boxplots
    # bp = ax.boxplot(
    #     data,
    #     vert=False,
    #     positions=positions,
    #     widths=0.20,
    #     showfliers=False
    # )
    ax.set_yticks(yticks)
    ax.set_yticklabels(labels)

    # scatter plots of the actual data
    # and line plots connecting the medians
    if fig_type in {"FA", "FV"}:
        imax = num_stories + 1
    else:
        imax = num_stories
    x_locs = []  # for the line plots
    y_locs = []
    x_medians = []
    y_medians = []
    for i in range(imax):
        ylocs = (
            np.random.normal(size=len(data[:, i])) * 0.05
            - bar_distance / 2.00
            + (i + 1 + index_shift)
        )
        ax.scatter(
            data[:, 2 * i],
            ylocs,
            edgecolor="C0",
            facecolor="white",
            marker="o",
            s=20,
            alpha=0.20,
        )
        x_locs.append(-bar_distance / 2.00 + (i + 1 + index_shift))
        x_medians.append(np.median(data[:, 2 * i]))
        ylocs = (
            np.random.normal(size=len(data[:, i])) * 0.05
            + bar_distance / 2.00
            + (i + 1 + index_shift)
        )
        ax.scatter(
            data[:, 2 * i + 1],
            ylocs,
            edgecolor="C1",
            facecolor="white",
            marker="^",
            s=20,
            alpha=0.20,
        )
        y_locs.append(+bar_distance / 2.00 + (i + 1 + index_shift))
        y_medians.append(np.median(data[:, 2 * i + 1]))
    # also connect the medians with lines
    ax.plot(x_medians, x_locs, color='C0')
    ax.plot(y_medians, y_locs, color='C1')

title_lst = archetype.upper().split("_")
fig.suptitle(f"{' '.join(title_lst)}", fontsize=14)
plt.tight_layout()
fig.text(0.5, 0.00, fig_type, ha="center")
plt.subplots_adjust(wspace=0, hspace=0)
# add text labels
for ax, i in zip(axs.flatten(), hzs):
    ax.text(
        0.95,
        0.95,
        f"HZ_LVL_{i+1}",
        ha="right",
        va="top",
        transform=ax.transAxes,
    )
xlim = ax.get_xlim()
for ax in axs.flatten():
    ax.set_xlim((xmin, xmax))
plt.tight_layout()
plt.show()
plt.close()
