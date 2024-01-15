"""
Plot buliding response
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from osmg.common import G_CONST_IMPERIAL


archetype = "scbf_9_ii"
hazard_level = "25"
gm_number = 1
plot_type = "ID"
direction = 'x'

arch_code, stories, rc = archetype.split("_")

res_df = pd.read_parquet(
    f"extra/structural_analysis/results/{archetype}/individual_files/{hazard_level}/"
    f"gm{gm_number}/results_{direction}.parquet"
)

res_df["FA"] /= G_CONST_IMPERIAL

time_vec = res_df["time"]
res_df.drop(columns="time", inplace=True)

df_sub = res_df[plot_type]

num_figs = df_sub.shape[1]

fig, axs = plt.subplots(num_figs, sharex=True, sharey=True)
for i, col in enumerate(df_sub):
    ax = axs[i]
    ax.plot(time_vec, df_sub[col], "k")

    # highlight peak and add value
    idx_max = np.abs(df_sub[col]).idxmax()
    ax.scatter(
        time_vec.at[idx_max],
        df_sub.at[idx_max, col],
        s=80,
        facecolor="white",
        edgecolor="black",
    )
    ax.text(
        time_vec.at[idx_max],
        df_sub.at[idx_max, col],
        f"{df_sub.at[idx_max, col]:.3f}",
        bbox={"facecolor": "white", "edgecolor": "black", "alpha": 0.50},
        fontsize="small",
    )

    ax.grid(which="both", linewidth=0.30)
    ax.set(ylabel=f"{plot_type}-{'-'.join(col)}")

plt.show()
plt.close()
