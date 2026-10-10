"""Barplot: unique second-level domains per ECH public name, split by ECH-in-DNS."""

import matplotlib.ticker as ticker
import polars as pl
import seaborn as sns

from ech_discovery.data.columns import Columns as C
from ech_discovery.data.mapper import Strings, ech_dns_rr_map


def plot_public_names_vs_slds(
    df,
    fig,
    ax,
    ech_dns_col: str = Strings.ech_in_dns,
    **kwargs,
):
    sns.barplot(
        df.with_columns(pl.col(ech_dns_col).replace_strict(ech_dns_rr_map)).sort(
            [pl.col(C.target_sld).sum().over(C.ech_public_name), ech_dns_col],
            descending=True,
        ),
        x=C.target_sld,
        y=C.ech_public_name,
        hue=ech_dns_col,
        ax=ax,
    )

    ax.xaxis.set_major_formatter(ticker.EngFormatter())
    ax.set(xscale="log")
    ax.set(ylabel=Strings.ech_public_name)
    ax.set(xlabel=Strings.domain_names)
    ax.set(**kwargs)
    ax.legend(title=None)
