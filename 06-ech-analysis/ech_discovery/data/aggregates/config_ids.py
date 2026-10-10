"""Domain counts per ECH config id, public name and role, bucketed by time."""

import polars as pl
from tqdm.auto import tqdm

from ech_discovery.data import loaders as loader
from ech_discovery.data.aggregates import common
from ech_discovery.data.columns import Columns as C
from ech_discovery.data.enrichment import ech, zdns
from ech_discovery.data.ranges import TimeRange

RESOLUTION = "1m"


def aggregate_config_ids_per_time(
    df,
    col=C.ts,
    resolution=RESOLUTION,
    group_by=[C.measurement, C.ech_public_name, C.ech_config_id, C.role, C.location],
):
    return (
        df.sort(col)
        .group_by_dynamic(col, every=resolution, group_by=group_by)
        .agg(pl.len())
        .collect()
    )


def _zdns_config_ids(time_range: TimeRange, resolution: str) -> list[pl.DataFrame]:
    files = common.files_in_range(
        loader.FileSelector(globs=[loader.zdns_glob]).get_files(), time_range
    )
    stats = []
    for file in tqdm(files, desc="zdns"):
        df = (
            pl.scan_parquet(file)
            .filter(zdns.ech_field)
            .with_columns(pl.col(C.ech_processed).list.get(0))
            .filter(pl.col(C.ts) == pl.col(C.ts).min().over(C.zdns_target))
            .unnest(C.ech_processed)
            .with_columns(pl.col(C.ech_config_id).cast(pl.UInt8))
        )
        agg = aggregate_config_ids_per_time(df, resolution=resolution)
        stats.append(agg.filter(pl.col(C.len).sum().over(C.ech_public_name, C.ech_config_id) > 2))
    return stats


def ech_config_id_per_time_and_public_name(time_range: TimeRange, resolution: str = RESOLUTION):
    dst_file = common.processed_file("ech_config_id_per_time_and_public_name", time_range)

    ech_files = loader.FileSelector(globs=[loader.ech_glob]).get_files()
    ech_quic_files = loader.FileSelector(globs=[loader.ech_quic_glob]).get_files()
    ech_stats = [
        aggregate_config_ids_per_time(
            common.without_multi_ech_domains(pl.scan_parquet(file).filter(ech.ech_accepted)),
            resolution=resolution,
        )
        for file in tqdm(common.files_in_range(ech_files + ech_quic_files, time_range), desc="ech")
    ]

    pl.concat(ech_stats + _zdns_config_ids(time_range, resolution)).write_parquet(dst_file)
