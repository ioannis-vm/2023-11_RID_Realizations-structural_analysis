"""
Generation of site hazard curves for ground motion selection for a
time-based assessment using OpenSHA PSHA output.

Note

  Assuming Poisson distributed earthquake occurence,


  p_occurence = 1 - exp(-t/T)

  where:
    P_exceedance is the probability of 1 or more occurences,
    t is the period of interest (1 year, 50 years, etc.),
    T is the return period (e.g. 475 years, 2475 years),
    1/T is called the `occurence rate` or `frequency`

"""

from scipy.interpolate import interp1d
import pandas as pd
import numpy as np
from src.util import store_info
from extra.structural_analysis.src.util import read_study_param
import matplotlib.pyplot as plt

# pylint: disable = invalid-name

np.seterr(divide="ignore")


def main() -> None:
    out_path = "extra/structural_analysis/results/site_hazard"

    # Parse OpenSHA output
    # fmt: off
    names = [
        "0p01", "0p02", "0p03", "0p05", "0p075", "0p1", "0p15", "0p2",
        "0p25", "0p3", "0p4", "0p5", "0p75", "1p0", "1p5", "2p0",
        "3p0", "4p0", "5p0", "7p5", "10p0",
    ]
    periods = [
        0.01, 0.02, 0.03, 0.05, 0.075, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4,
        0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 7.5, 10.0,
    ]
    # fmt: on
    hzrd_crv_files = [f"{out_path}/{name}.txt" for name in names]

    dfs_sub = []

    for filepath in hzrd_crv_files:
        with open(filepath, "r", encoding="utf-8") as f:
            line = f.read()
        contents = line.split("\n")
        i_begin = -1
        num_points = -1
        for i, c in enumerate(contents):
            words = c.split(" ")
            if words[0] == "X," and words[1] == "Y" and words[2] == "Data:":
                i_begin = i + 1
            if words[0] == "Num":
                num_points = int(words[2])
        i_end = i_begin + num_points
        data = np.genfromtxt(contents[i_begin:i_end])
        df = pd.DataFrame(data[:, 1], index=data[:, 0], columns=["MAPE"])
        df.index.name = "Sa"
        df["MAFE"] = -np.log(1.00 - df["MAPE"])
        dfs_sub.append(df)

    df = pd.concat(dfs_sub, axis=1, keys=periods)
    df.columns.names = ["T", "Type"]

    df_mafe = df.xs("MAFE", axis=1, level=1)  # type: ignore

    # save the hazard curves
    df.to_csv(store_info(f"{out_path}/hazard_curves.csv"))

    # Obtain period-specific hazard curve
    # Interpolate available hazard curves
    t_bar = float(
        read_study_param("extra/structural_analysis/data/scbf_9_ii/period_closest")
    )
    target_mafes: list[float] = []
    for acc in df_mafe.index:
        vec = np.log(df_mafe.loc[acc, :])
        f = interp1d(periods, vec, kind="linear")
        target_mafes.append(np.exp(float(f(t_bar))))  # type: ignore
    df[("target", "MAFE")] = target_mafes

    # Define interpolation functions for the period-specific hazard curve
    # Interpolate: From MAFE λ to intensity e [g]
    def fHazMAFEtoSa(mafe):
        """
        Interpolate Sa for a given MAFE
        """
        temp1 = interp1d(
            np.log(df[("target", "MAFE")]).to_numpy(),
            np.log(df.index.to_numpy()),
            kind="cubic",
        )
        return np.exp(temp1(np.log(mafe)))

    # Interpolate: Inverse (From intensity e [g] to MAFE λ)
    def fHazSatoMAFE(sa):
        """
        Interpolate MAFE for a given Sa
        """
        temp2 = interp1d(
            np.log(df.index).to_numpy(),
            np.log(df[("target", "MAFE")]).to_numpy(),
            kind="cubic",
            fill_value='extrapolate',
        )
        return np.exp(temp2(np.log(sa)))

    # Specify Intensity range
    if t_bar <= 1.00:
        SaMin = 0.05
    else:
        SaMin = 0.05 / t_bar
    SaMax = fHazMAFEtoSa(1e-4)
    SaMin = fHazMAFEtoSa(0.50)

    # Split intensity range to m intervals

    m = int(read_study_param("extra/structural_analysis/data/study_vars/m"))
    # m_sub = int(read_study_param("extra/structural_analysis/data/study_vars/m_sub"))

    # Determine interval midpoints and endpoints

    e_vec = np.linspace(SaMin, SaMax, m * 2 + 1)
    mafe_vec = fHazSatoMAFE(e_vec)
    mafe_des = 1.0 / 475.0
    mafe_mce = 1.0 / 2475.0
    e_des = fHazMAFEtoSa(mafe_des)
    e_mce = fHazMAFEtoSa(mafe_mce)

    # + this makes sure that two of the midpoints
    #   will fall exactly on the design and MCE level
    #   scenarios.

    k = -1
    if mafe_vec[-1] < mafe_des < mafe_vec[0]:
        # identify index closest to design lvl
        dif = np.full(m * 2 + 1, 0.00)
        for i, e in enumerate(e_vec):
            dif[i] = e_des - e
        k = 2 * int(np.argmin(dif[1::2] ** 2)) + 1
        corr = np.full(len(e_vec), 0.00)
        corr[0 : k + 1] = np.linspace(0, dif[k], k + 1)
        corr[k::] = np.linspace(dif[k], 0, m * 2 - k + 1)
        e_vec = e_vec + corr
        mafe_vec = fHazSatoMAFE(e_vec)

    if mafe_vec[-1] < mafe_mce < mafe_vec[0]:
        # identify index closest to MCE lvl
        dif = np.full(m * 2 + 1, 0.00)
        for i, e in enumerate(e_vec):
            dif[i] = e_mce - e
        k2 = 2 * np.argmin(dif[1::2] ** 2) + 1
        corr = np.full(len(e_vec), 0.00)
        corr[k + 1 : k2] = np.linspace(0, dif[k2], k2 - (k + 1))
        corr[k2::] = np.linspace(dif[k2], 0, m * 2 - k2 + 1)
        e_vec = e_vec + corr
        mafe_vec = fHazSatoMAFE(e_vec)

    e_Endpoints = e_vec[::2]
    MAFE_Endpoints = mafe_vec[::2]
    e_Midpoints = e_vec[1::2]
    MAFE_Midpoints = mafe_vec[1::2]
    MAPE_Midpoints = 1 - np.exp(-MAFE_Midpoints)
    return_period_midpoints = 1 / MAFE_Midpoints

    # Wed May 29 03:00:39 AM PDT 2024
    # We add four extra hazard levels beyond 25
    m_adjusted = m + 4

    mafe_beyond = np.array(
        (1.0 / 20000.00, 1.0 / 80000.00, 1.0 / 250000.00, 1.0 / 1000000.0)
    )
    e_beyond = fHazMAFEtoSa(mafe_beyond)

    # adjust endpoints
    e_Endpoints[-1] = np.mean((e_Midpoints[-1], e_beyond[0]))
    MAFE_Endpoints[-1] = fHazSatoMAFE(e_Endpoints[-1])
    endpoints_beyond = [
        np.mean((e_beyond[0], e_beyond[1])),
        np.mean((e_beyond[1], e_beyond[2])),
        np.mean((e_beyond[2], e_beyond[3])),
        (e_beyond[3] - np.mean((e_beyond[2], e_beyond[3]))) * 2.0
        + np.mean((e_beyond[2], e_beyond[3])),
    ]
    mafe_endpoints_beyond = fHazSatoMAFE(endpoints_beyond)

    e_Midpoints = np.concatenate((e_Midpoints, e_beyond))
    MAFE_Midpoints = np.concatenate((MAFE_Midpoints, mafe_beyond))
    e_Endpoints = np.concatenate((e_Endpoints, endpoints_beyond))
    MAFE_Endpoints = np.concatenate((MAFE_Endpoints, mafe_endpoints_beyond))

    delta_e = np.array(
        [e_Endpoints[i + 1] - e_Endpoints[i] for i in range(m_adjusted)]
    )
    delta_lamda = np.array(
        [MAFE_Endpoints[i] - MAFE_Endpoints[i + 1] for i in range(m_adjusted)]
    )

    MAPE_Midpoints = 1 - np.exp(-MAFE_Midpoints)
    return_period_midpoints = 1 / MAFE_Midpoints

    def plot_curve():
        """
        Plots the hazard level midpoints/endpoitns on the curve.
        """

        fig, ax = plt.subplots()
        ax.plot(df[("target", "MAFE")], "-", label="Hazard Curve", color="black")
        ax.scatter(
            e_Endpoints,
            MAFE_Endpoints,
            s=80,
            facecolors="none",
            edgecolors="k",
            label="Interval Endpoints",
        )
        ax.scatter(
            e_Midpoints,
            MAFE_Midpoints,
            s=40,
            facecolors="k",
            edgecolors="k",
            label="Interval Midpoints",
        )
        for i, (x, y) in enumerate(zip(e_Midpoints, MAFE_Midpoints), 1):
            ax.text(x, y, str(i), ha="center", va="bottom")
        ax.grid(which="both", linewidth=0.30)
        ax.axvline(SaMin, color="k", linestyle="dashed")
        ax.axvline(SaMax, color="k", linestyle="dashed")
        ax.set(yscale="log")
        ax.set(xlabel="$x$ [g]")
        ax.set(ylabel=f"$λ(Sa(T={t_bar:.2f}) > x)$")
        plt.show()
        plt.close()

    # store hazard curve interval data
    interv_df = pd.DataFrame(
        np.column_stack(
            (
                e_Midpoints,
                delta_e,
                delta_lamda,
                MAFE_Midpoints,
                MAPE_Midpoints,
                return_period_midpoints,
            )
        ),
        columns=["e", "de", "dl", "freq", "prob", "T"],
        index=range(1, m_adjusted + 1),
    )
    interv_df.to_csv(store_info(f"{out_path}/Hazard_Curve_Interval_Data.csv"))

    # Obtain Uniform Hazard Spectra for each midpoint

    uhs_dfs = []

    spectrum_idx = 0
    for spectrum_idx in range(m_adjusted):
        rs: list[float] = []
        target_mafe = MAFE_Midpoints[spectrum_idx]
        for period in periods:
            log_mafe = np.log(df[(period, "MAFE")].to_numpy())
            log_sa = np.log(df.index.to_numpy())
            log_target_mafe = np.log(target_mafe)
            f = interp1d(log_mafe, log_sa, kind="cubic", fill_value='extrapolate')
            log_target_sa = float(f(log_target_mafe))  # type: ignore
            target_sa = np.exp(log_target_sa)
            rs.append(target_sa)
        uhs = np.column_stack((periods, rs))
        uhs_df = pd.DataFrame(uhs, columns=["T", "Sa"])
        uhs_df.set_index("T", inplace=True)
        uhs_dfs.append(uhs_df)

    # write UHS data to files
    for i, uhs_df in enumerate(uhs_dfs):
        uhs_df.to_csv(store_info(f"{out_path}/UHS_{i + 1}.csv"))

    def plot_uhs_spectra():
        uhs_df = pd.concat(uhs_dfs, axis=1)
        uhs_df.columns = [i + 1 for i in range(m_adjusted)]
        fig, ax = plt.subplots()
        for col in uhs_df.columns:
            ax.plot(uhs_df[col], "k")
        ax.grid(which="both")
        ax.set(xscale="log", yscale="log")
        ax.set(xlabel="Period [s]")
        ax.set(ylabel="RotD50 Sa [g]")
        ax.set(title="Uniform hazard spectra.")
        plt.show()
        plt.close()


if __name__ == '__main__':
    main()
