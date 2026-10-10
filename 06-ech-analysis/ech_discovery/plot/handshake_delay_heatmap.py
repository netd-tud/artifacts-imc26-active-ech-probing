"""Heatmap: distribution of the TLS-handshake delay of ECH per public name."""

import matplotlib.ticker as ticker
import seaborn as sns

from ech_discovery.data.columns import Columns as C
from ech_discovery.data.mapper import Strings


def plot_handshake_delay_heatmap(df, fig, ax):
    sns.histplot(
        df,
        x=C.hs_duration_diff,
        y=C.ech_public_name,
        weights=C.len_percent,
        binwidth=0.5,
        binrange=(-20, 20),
        cbar=True,
        legend=False,
        cmap="Spectral_r",
        vmin=0,
        vmax=9,
        cbar_kws={"ticks": [0, 2, 4, 6, 8], "format": "{x} %", "aspect": 10},
    )
    ax.set(xlim=(-15, 15), ylim=(-0.5, 1.5))
    ax.set(ylabel=Strings.public_name_split, xlabel=Strings.delay)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(5))
    ax.xaxis.set_minor_locator(ticker.MultipleLocator(1))
