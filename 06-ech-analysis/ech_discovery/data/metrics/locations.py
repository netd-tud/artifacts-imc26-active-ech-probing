from datetime import datetime, time, timedelta

import polars as pl

from ech_discovery.data import loaders as loader
from ech_discovery.data.columns import Columns as C
from ech_discovery.data.ranges import TimeRange

CLOUD_LOCATIONS = [
    "africa-south1",
    "asia-east2",
    "australia-southeast1",
    "europe-west10",
    "southamerica-east1",
    "us-west2",
]

ROLES = ["ech", "ech-quic"]

# How far a measurement may sit from the target date and still count as that round - beyond
# this a location counts as not measured rather than being matched to an unrelated date.
MAXDIFF = timedelta(days=30)

# A location is an outlier when its count falls below this fraction of its set's median for
# the same role - catches broken runs without flagging the ~1% spread that is normal.
OUTLIER_THRESHOLD = 0.7

DOMAINS = "domains"
GROUP_MEDIAN = "group_median"
STATUS = "status"
LOCATION_SET = "location_set"
MAX_DIFF_PCT = "max_diff_pct"
EXCLUDED = "excluded"
MEASUREMENT_DATES = "measurement_dates"
_DISTANCE = "distance"


def location_sets(primary_location: str) -> dict[str, list[str]]:
    """The cloud vantage points on their own, and together with the primary one."""
    return {
        "cloud": CLOUD_LOCATIONS,
        f"cloud+{primary_location}": CLOUD_LOCATIONS + [primary_location],
    }


def _target_date(counts: pl.DataFrame, time_range: TimeRange) -> datetime:
    """Day of the last cloud round in `time_range`, the date every location is compared at."""
    day = (
        counts.filter(time_range.expr(), pl.col(C.location).is_in(CLOUD_LOCATIONS))
        .select(pl.col(C.measurement).max().dt.date())
        .item()
    )
    return datetime.combine(day, time.min)


def _closest_measurements(counts: pl.DataFrame, target: datetime) -> pl.DataFrame:
    """One row per location and role: the measurement nearest `target` within `MAXDIFF`.

    A measurement on or after `target` wins over a closer earlier one, so a location measured
    continuously (rather than in rounds) is matched to the same day as the cloud locations
    instead of the evening before.
    """
    return (
        counts.with_columns((pl.col(C.measurement) - target).abs().alias(_DISTANCE))
        .filter(pl.col(_DISTANCE) < MAXDIFF)
        .sort(pl.col(C.measurement) < target, _DISTANCE)
        .group_by(C.location, C.role)
        .first()
        .select(C.location, C.role, C.measurement, pl.col(C.target_sld).alias(DOMAINS))
    )


def _flag(df: pl.DataFrame) -> pl.DataFrame:
    """Add `group_median` and `status`, with the median taken over the rows of `df` alone."""
    return df.with_columns(pl.col(DOMAINS).median().over(C.role).alias(GROUP_MEDIAN)).with_columns(
        pl.when(pl.col(DOMAINS).is_null())
        .then(pl.lit("missing"))
        .when(pl.col(DOMAINS) < OUTLIER_THRESHOLD * pl.col(GROUP_MEDIAN))
        .then(pl.lit("outlier"))
        .otherwise(pl.lit("ok"))
        .alias(STATUS)
    )


def domains_per_location(time_range: TimeRange, primary_location: str = "tud") -> pl.DataFrame:
    """Accepted-ECH domains per location and role around `time_range`'s cloud round.

    One block of rows per location set, each flagged against its own median so adding the
    primary location cannot skew the cloud-only comparison, and vice versa.
    """
    counts = loader.ech_sld_counts().collect()
    measurements = _closest_measurements(counts, _target_date(counts, time_range))
    return pl.concat(
        _flag(
            pl.DataFrame({C.location: locations})
            .join(pl.DataFrame({C.role: ROLES}), how="cross")
            .join(measurements, on=[C.location, C.role], how="left", validate="1:1")
        ).with_columns(pl.lit(set_name).alias(LOCATION_SET))
        for set_name, locations in location_sets(primary_location).items()
    )


def domains_per_location_spread(
    time_range: TimeRange, primary_location: str = "tud"
) -> pl.DataFrame:
    """Per location set and role: how far apart the highest and lowest location are, as a
    percentage of the lowest, plus the locations left out and why.

    Computed over the locations flagged `ok` only -- across all of them the number reflects
    whichever run broke rather than genuine cross-location variation.
    """
    results = domains_per_location(time_range, primary_location)
    group = [LOCATION_SET, C.role]
    excluded = (
        results.filter(pl.col(STATUS) != "ok")
        .group_by(group)
        .agg((pl.col(C.location) + " (" + pl.col(STATUS) + ")").sort().alias(EXCLUDED))
    )
    return (
        results.filter(pl.col(STATUS) == "ok")
        .group_by(group)
        .agg(
            pl.col(DOMAINS).max().alias("max"),
            pl.col(C.location).sort_by(DOMAINS).last().alias("max_location"),
            pl.col(DOMAINS).min().alias("min"),
            pl.col(C.location).sort_by(DOMAINS).first().alias("min_location"),
            pl.col(C.measurement).dt.date().unique().sort().alias(MEASUREMENT_DATES),
        )
        .with_columns(((pl.col("max") - pl.col("min")) / pl.col("min") * 100).alias(MAX_DIFF_PCT))
        .join(excluded, on=group, how="left", validate="1:1")
        .with_columns(pl.col(EXCLUDED).fill_null([]))
        .sort(group)
    )
