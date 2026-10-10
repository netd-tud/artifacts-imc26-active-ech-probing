from pathlib import Path

import polars as pl
import polars.selectors as cs
from tqdm.auto import tqdm

from ech_discovery.data import loaders as loader
from ech_discovery.data.aggregates import common
from ech_discovery.data.columns import Columns as C
from ech_discovery.data.enrichment import ech
from ech_discovery.data.ranges import TimeRange

ROLE_GLOBS = {"ech": loader.ech_glob, "ech-quic": loader.ech_quic_glob}

hs_duration_diff = pl.col(C.hs_duration_with_ech) - pl.col(C.hs_duration_without_ech)

_diff_ms = pl.col(C.hs_duration_diff) / 1_000


def _files(time_range: TimeRange, role: str | None = None) -> list[Path]:
    """TCP-TLS and QUIC measurement files in `time_range`, or only those of `role`."""
    globs = list(ROLE_GLOBS.values()) if role is None else [ROLE_GLOBS[role]]
    return common.files_in_range(loader.FileSelector(globs=globs).get_files(), time_range)


def _accepted(files: Path | list[Path]) -> pl.LazyFrame:
    return common.without_multi_ech_domains(pl.scan_parquet(files).filter(ech.ech_accepted))


def _dispersion_stats() -> list[pl.Expr]:
    """Std, median absolute deviation and IQR (25/75) of `hs_duration_diff`, in ms."""
    return [
        _diff_ms.std().alias(C.hs_duration_diff + "-std"),
        (_diff_ms - _diff_ms.median()).abs().median().alias(C.hs_duration_diff + "-mad"),
        _diff_ms.quantile(0.25).alias(C.hs_duration_diff + "-q25"),
        _diff_ms.quantile(0.75).alias(C.hs_duration_diff + "-q75"),
    ]


def _timing_dst_file(name: str, time_range: TimeRange, freq: str | None) -> Path:
    return common.processed_file(name if freq is None else f"{name}_fine_{freq}", time_range)


def _time_slot(freq: str | None) -> str:
    return C.measurement if freq is None else C.ts_bucket


def latency_stats(file: Path, dst_file: Path):
    """Handshake duration percentiles per role, measurement and location (in ms)."""
    durations = pl.col(C.hs_duration_with_ech, C.hs_duration_without_ech)
    _accepted(file).group_by(C.role, C.measurement, C.location).agg(
        durations.median().name.suffix("-median"),
        durations.mean().name.suffix("-mean"),
        *(durations.quantile(q / 100).name.suffix(f"-q{q}") for q in (90, 95, 99)),
        hs_duration_diff.median().alias(C.hs_duration_diff + "-median"),
    ).with_columns(
        # transform to ms
        cs.numeric() / 1000
    ).sink_parquet(dst_file)


def meas_duration_stats(file: Path, dst_file: Path):
    """Measurement duration per role, measurement and location, over all connections."""
    pl.scan_parquet(file).group_by(C.role, C.measurement, C.location).agg(
        (pl.col(C.ts).max() - pl.col(C.ts).min()).alias(C.meas_duration),
    ).sink_parquet(dst_file)


def aggregate_latency_per_measurement(time_range: TimeRange):
    for file in tqdm(_files(time_range)):
        latency_stats(file, file.with_name("latency-stats_" + file.name))
        meas_duration_stats(file, file.with_name("meas-duration_" + file.name))


def _filter_ech_accepted_timing_diffs(
    time_range: TimeRange, freq: str | None
) -> list[pl.LazyFrame]:
    """Per-file frames with `hs_duration_diff` (with-ECH minus without-ECH) added, and, if
    `freq` is given, a `ts_bucket` column truncated to that width"""
    dfs = []
    for file in tqdm(_files(time_range)):
        df = _accepted(file).with_columns(hs_duration_diff.alias(C.hs_duration_diff))
        if freq is not None:
            df = df.with_columns(pl.col(C.ts).dt.truncate(freq).alias(C.ts_bucket))

        if df.select(pl.len()).collect().item() > 0:
            dfs.append(df)

    return dfs


def aggregate_timing_diff_histogram_per_measurement_and_public_name(
    time_range: TimeRange, dst_file: Path | None = None, freq: str | None = None
):
    """With/without-ECH handshake timing differences, bucketed into a histogram per
    (time slot, public name, role, location).
    """
    if dst_file is None:
        dst_file = _timing_dst_file("timing_statistics", time_range, freq)

    dfs = _filter_ech_accepted_timing_diffs(time_range, freq)
    group_by = [_time_slot(freq), C.ech_public_name, C.role, C.location]
    diffs = [ech.agg_timing_differences(df, every="200i", group_by=group_by) for df in dfs]
    pl.concat(diffs).write_parquet(dst_file)


def aggregate_timing_diff_dispersion_per_measurement(
    time_range: TimeRange, dst_file: Path | None = None, freq: str | None = None
):
    """Std, median absolute deviation, and IQR (25/75) of the with/without-ECH handshake
    timing difference, per (time slot, role, location) across all public names combined"""
    if dst_file is None:
        dst_file = _timing_dst_file("timing_dispersion", time_range, freq)

    dfs = _filter_ech_accepted_timing_diffs(time_range, freq)
    group_by = [_time_slot(freq), C.role, C.location]
    stats = [df.group_by(group_by).agg(_dispersion_stats()).collect() for df in dfs]
    pl.concat(stats).write_parquet(dst_file)


def aggregate_timing_diff_dispersion_per_hour_of_day(
    time_range: TimeRange, dst_file: Path | None = None
):
    """Std, median absolute deviation, and IQR (25/75) of the with/without-ECH handshake
    timing difference, per (hour of day, role, location), folding every day in the range
    together into one 24-hour cycle"""
    if dst_file is None:
        dst_file = common.processed_file("timing_dispersion_time_of_day", time_range)

    stats = []
    for role in ROLE_GLOBS:
        files = _files(time_range, role)
        locations = sorted({common.extract_location(f) for f in files})
        for location in tqdm(locations, desc=role):
            location_files = [f for f in files if common.extract_location(f) == location]
            df = _accepted(location_files).select(
                pl.col(C.ts).dt.hour().alias(C.ts_hour),
                hs_duration_diff.alias(C.hs_duration_diff),
            )
            stats.append(
                df.group_by(C.ts_hour)
                .agg(_dispersion_stats())
                .with_columns(pl.lit(role).alias(C.role), pl.lit(location).alias(C.location))
                .collect()
            )

    pl.concat(stats).write_parquet(dst_file)
