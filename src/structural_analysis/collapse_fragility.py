"""
Use analysis results to derive the collapse fragility of each
archetype
"""

import numpy as np
import pandas as pd
from scipy.special import binom
from scipy.stats import norm
from scipy.optimize import minimize
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt
from extra.structural_analysis.src.util import read_study_param


def process_response(filepath):
    """
    Process the response file
    """
    df = pd.read_parquet(filepath)
    df.columns.names = ("edp", "location", "direction")

    num_runs = len(df)

    drift_threshold = 0.06

    collapse = df["PID"].max(axis=1) > drift_threshold

    collapse_idx = collapse[collapse == True].index
    num_collapse = len(collapse_idx)

    return num_collapse, num_runs


def get_sa(hz, base_period):
    """
    Read a target spectrum from a file.
    """
    # determine Sa at those levels
    spectrum = pd.read_csv(
        f"extra/structural_analysis/results/site_hazard/UHS_{hz}.csv",
        index_col=0,
        header=0,
    )

    ifun = interp1d(spectrum.index.to_numpy(), spectrum.to_numpy().reshape(-1))
    current_sa = float(ifun(base_period))
    return current_sa


def neg_log_likelihood(x, njs, zjs, xjs):
    """
    Calculates the negative log likelihood of observing the given data
    under the specified distribution parameters
    """
    theta, beta = x
    phi = norm.cdf(np.log(xjs / theta) / beta)
    logl = np.sum(
        np.log(binom(njs, zjs))
        + zjs * np.log(phi)
        + (njs - zjs) * np.log(1.00 - phi)
    )
    return -logl


def main():
    archetype = 'scbf_9_ii'
    num_hz = int(read_study_param("extra/structural_analysis/data/study_vars/m"))
    base_period = float(
        read_study_param(
            f"extra/structural_analysis/data/{archetype}/period_closest"
        )
    )
    filepaths = [
        f"extra/structural_analysis/results/"
        f"{archetype}/edp/{x + 1}/response.parquet"
        for x in range(num_hz)
    ]

    zjs = []
    njs = []
    for filepath in filepaths:
        z, n = process_response(filepath)
        zjs.append(z)
        njs.append(n)
    xjs = []
    for hz in [f"{i + 1}" for i in range(num_hz)]:
        xjs.append(get_sa(hz, base_period))

    zjs = np.array(zjs, dtype=float)
    njs = np.array(njs, dtype=float)
    xjs = np.array(xjs, dtype=float)

    x0 = np.array((3.00, 0.40))

    res = minimize(
        neg_log_likelihood,
        x0,
        method="nelder-mead",
        args=(njs, zjs, xjs),
        bounds=((0.0, 20.00), (0.20, 0.90)),
    )

    median = res.x[0]
    beta = res.x[1]

    print(f'{median=}')
    print(f'{beta=}')

    x = np.linspace(0.0, 3.0 * median, 1000)
    y = norm.cdf(np.log(x / median) / beta)

    _, ax = plt.subplots()
    ax.plot(x, y)
    ax.scatter(xjs, zjs / njs)
    plt.show()


if __name__ == '__main__':
    main()
