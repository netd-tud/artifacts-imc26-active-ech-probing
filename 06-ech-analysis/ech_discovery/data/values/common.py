from collections.abc import Callable
from functools import partial
import re

import polars as pl

from ech_discovery.data.columns import Columns as C
from ech_discovery.data.ranges import DEFAULT_RANGES, RANGES, TimeRange

RANGES_FOR_VALUES = tuple(RANGES[name] for name in DEFAULT_RANGES)

measurement_location = "tud"

roles = {
    "Ech": "ech",
    "EchQuic": "ech-quic",
}


def range_key(time_range: TimeRange, name: str) -> str:
    return time_range.name + name[0].upper() + name[1:]


def name_part(value: str) -> str:
    """Data name as a value-name fragment: `ech-quic` -> `EchQuic`, `cloud+tud` -> `CloudTud`."""
    return "".join(part.capitalize() for part in re.split(r"[-+]", value))


Key = Callable[[str], str]


def key_fn(time_range: TimeRange) -> Key:
    """`range_key` with the range pre-bound."""
    return partial(range_key, time_range)


def pct_label(name: pl.Expr) -> pl.Expr:
    """`name` and the row's share, as "name (12%)"."""
    return (
        name
        + pl.lit(" (")
        + pl.col(C.len_percent).round(0).cast(pl.Int64).cast(pl.String)
        + pl.lit("%)")
    )


def and_join(df: pl.LazyFrame, col: str = "label") -> pl.LazyFrame:
    """Single-row frame joining `df`'s `col` as "a, b, and c" -- 'and' only before the last."""
    return (
        df.select(pl.col(col).implode().alias("labels"))
        .with_columns(pl.col("labels").list.len().alias("n"))
        .select(
            pl.when(pl.col("n") <= 1)
            .then(pl.col("labels").list.join(""))
            .when(pl.col("n") == 2)
            .then(pl.col("labels").list.join(" and "))
            .otherwise(
                pl.col("labels").list.slice(0, pl.col("n") - 1).list.join(", ")
                + pl.lit(", and ")
                + pl.col("labels").list.slice(pl.col("n") - 1, 1).list.join("")
            )
        )
    )
