"""Lineplot: share of connections per TLS-handshake delay of ECH, per public name."""

import seaborn as sns

from ech_discovery.data.columns import Columns as C


def plot_handshake_delay_share(df, fig, ax, style=None, col=C.len_percent):
    sns.lineplot(
        df,
        x=C.hs_duration_diff,
        y=col,
        hue=C.ech_public_name,
        style=style,
        ax=ax,
    )

    ax.legend(ncol=2, bbox_to_anchor=(0.5, 1), loc="lower center")
    ax.set(xlim=(-15, 15))
