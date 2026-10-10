"""Interactive altair chart: cumulative handshake-delay difference with a measurement slider."""

import polars as pl

from ech_discovery import config
from ech_discovery.data.columns import Columns as C


def plot_handshake_delay_interactive(df):
    import altair as alt

    df = df.with_columns(pl.col(C.measurement).rank("dense").alias("rank"))
    max_meas = df.select(pl.col("rank").max()).item()

    slider = alt.binding_range(min=1, max=max_meas, step=1)
    measurement = alt.selection_point(bind=slider, fields=["rank"], value=max_meas, name="rank")
    selection = alt.selection_point(fields=[C.ech_public_name], bind="legend")
    alt.data_transformers.disable_max_rows()
    return (
        df.filter(
            pl.col(C.hs_duration_diff) > -15,
            pl.col(C.hs_duration_diff) < 15,
        )
        .filter(pl.col(C.ech_public_name).is_in(config.MAIN_ECH_PUBLIC_NAMES))
        .rename({C.len_percent_cum: "cum"})
        .plot.line(
            x=C.hs_duration_diff,
            y="cum",
            color=f"{C.measurement}:O",
            strokeDash=C.ech_public_name,
            opacity=alt.condition(selection, alt.value(1), alt.value(0.1)),
        )
        .add_params(measurement, selection)
        .transform_filter(
            alt.FieldRangePredicate("rank", [measurement.rank - 5, measurement.rank]),
        )
    )
