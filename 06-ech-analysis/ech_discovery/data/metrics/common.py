"""Shared helpers for reducing processed aggregates down to single paper values."""

import polars as pl

from ech_discovery.data.columns import Columns as C
from ech_discovery.data.ranges import TimeRange


def latest_of(df: pl.LazyFrame, time_range: TimeRange, col: str = C.measurement) -> pl.LazyFrame:
    """Every row at `col`'s max value within `time_range` (both bounds honored, open ones
    matching everything on that side -- see `TimeRange.expr`).

    Not pinned to `time_range.end`: whichever `col` value is actually the
    largest within the range wins, so a role/location whose last file landed
    a few days before the nominal range end is still picked up correctly,
    instead of falling back to a separately-resolved sentinel end date.
    Doesn't filter location -- use `latest` where the query needs one.
    More than one row commonly shares that max `col` value (e.g. the
    ECH-in-DNS true/false split, or one row per status/error-reason/domain
    that a single measurement snapshot produces) -- every one of them
    survives, so callers must reduce with an aggregating `.select`
    (`.sum()`, `.n_unique()`, ...) or a `.group_by().agg()`, not a bare
    column read that assumes a single row.
    """
    df = df.filter(time_range.expr(col))
    return df.filter(pl.col(col) == pl.col(col).max())


def latest(
    df: pl.LazyFrame, time_range: TimeRange, location: str, col: str = C.measurement
) -> pl.LazyFrame:
    """Rows at `location` from the latest `col` within `time_range` (see `latest_of`)."""
    return latest_of(df.filter(pl.col(C.location) == location), time_range, col)
