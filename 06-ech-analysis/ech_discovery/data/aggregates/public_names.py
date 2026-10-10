from pathlib import Path

import polars as pl
from tqdm.auto import tqdm

from ech_discovery import config
from ech_discovery.data import loaders as loader
from ech_discovery.data.aggregates import common
from ech_discovery.data.aggregates.common import cv
from ech_discovery.data.columns import Columns as C
from ech_discovery.data.enrichment import ech
from ech_discovery.data.mapper import Strings
from ech_discovery.data.ranges import TimeRange


def counts(file: Path, dst_file: Path):
    """Domains per public name and measurement, tagged by outcome (`kind`)."""
    df_ech = common.without_multi_ech_domains(pl.scan_parquet(file))
    df_ech = ech.replace_nordvpn_public_name(df_ech)
    df_ech = common.with_ech_in_dns(df_ech, file)

    accepted = ech.agg_public_names_per_measurement(df_ech.filter(ech.ech_accepted))
    failed_retry = ech.agg_public_names_per_measurement(
        df_ech.filter(ech.retry_offered_but_not_accepted)
    )

    pl.concat(
        [
            accepted.with_columns(pl.lit("accepted").alias(C.kind)),
            failed_retry.with_columns(pl.lit("failed_retry").alias(C.kind)),
        ]
    ).sink_parquet(dst_file)


def _quic_locations() -> list[str]:
    return [p.name for p in (config.RAW_DATA_DIR / "gcloud" / "ech").glob("*")] + ["tud"]


def _closest_quic_files(file_ech: Path, locations: list[str] | None = None) -> list[Path]:
    """Closest-by-date QUIC file for each of `locations` (default: every known vantage point)."""
    if locations is None:
        locations = _quic_locations()
    closest_files = []
    for location in locations:
        ech_quic_files = loader.FileSelector(
            globs=[loader.ech_quic_glob], regex_filter=location
        ).get_files()
        closest_quic_file = common.get_closest(
            common.extract_date(file_ech), ech_quic_files, direction="backward"
        )
        if closest_quic_file is not None:
            closest_files.append(closest_quic_file)
    return closest_files


def _same_day_files(file_ech: Path) -> list[Path]:
    """Every location's TCP run from `file_ech`'s day, each with its closest earlier QUIC run."""
    day = common.extract_date(file_ech).date()
    tcp_files = [
        f
        for f in loader.FileSelector(globs=[loader.ech_glob]).get_files()
        if common.extract_date(f).date() == day
    ]
    files = list(tcp_files)
    for tcp_file in tcp_files:
        files += _closest_quic_files(tcp_file, [common.extract_location(tcp_file)])
    return files


def _public_name_counts(files: list[Path], file_ech: Path) -> pl.LazyFrame:
    """Domains per public name over `files`, with the ECH-in-DNS flag from `file_ech`'s snapshot.

    Also adds one row tagged `config.PUBLIC_NAME_NOT_CLOUDFLARE_META`: the deduplicated domain
    count across every public name other than Cloudflare/Meta. That can't be derived later by
    summing the per-public-name rows above -- the same SLD can be configured under more than one
    of those smaller deployments at once, so summing would double count it. Deduping has to
    happen here, before any public-name grouping.
    """
    df_ech = common.without_multi_ech_domains(pl.scan_parquet(files).filter(ech.ech_accepted))
    df_ech = common.with_ech_in_dns(df_ech, file_ech)

    schema_cols = [C.ech_public_name, Strings.ech_in_dns, C.target_sld]
    by_public_name = ech.agg_public_names_per_measurement(
        df_ech, group_by=[C.ech_public_name]
    ).select(schema_cols)
    not_cloudflare_meta = (
        ech.agg_public_names_per_measurement(
            df_ech.filter(~pl.col(C.ech_public_name).is_in(config.MAIN_ECH_PUBLIC_NAMES_ALL)),
            group_by=[],
        )
        .with_columns(pl.lit(config.PUBLIC_NAME_NOT_CLOUDFLARE_META).alias(C.ech_public_name))
        .select(schema_cols)
    )

    return pl.concat([by_public_name, not_cloudflare_meta]).with_columns(
        pl.lit(common.extract_date(file_ech)).alias(C.measurement)
    )


def total_counts(file_ech: Path, dst_file: Path, dst_file_all_locations: Path):
    """Domains per public name over one measurement plus the closest QUIC run at its location."""
    own_location = [file_ech] + _closest_quic_files(file_ech, [common.extract_location(file_ech)])
    _public_name_counts(own_location, file_ech).sink_parquet(dst_file)
    _public_name_counts(_same_day_files(file_ech), file_ech).sink_parquet(dst_file_all_locations)


def aggregate_per_measurement(time_range: TimeRange):
    ech_files = loader.FileSelector(globs=[loader.ech_glob]).get_files()
    ech_quic_files = loader.FileSelector(globs=[loader.ech_quic_glob]).get_files()

    for file in tqdm(common.files_in_range(ech_files + ech_quic_files, time_range)):
        counts(file, file.with_name("stats_" + file.name))


def aggregate_totals(time_range: TimeRange):
    ech_files = loader.FileSelector(globs=[loader.ech_glob], regex_filter="tud").get_files()

    for file in tqdm(common.files_in_range(ech_files, time_range)):
        total_counts(
            file,
            file.with_name("total_stats_" + file.name),
            file.with_name("total_stats_all_locations_" + file.name),
        )


def agg_quic_only_domains(time_range: TimeRange, dst_file: Path | None = None):
    """SLDs accepting ECH via QUIC but not via TCP on the closest TCP measurement day."""
    if dst_file is None:
        dst_file = common.processed_file("quic_only_domains", time_range)

    ech_files = loader.FileSelector(globs=[loader.ech_glob]).get_files()
    quic_files = loader.FileSelector(globs=[loader.ech_quic_glob]).get_files()

    dfs = []
    for quic_file in tqdm(common.files_in_range(quic_files, time_range)):
        closest_ech_file = common.get_closest(
            common.extract_date(quic_file), ech_files, direction="backward"
        )
        if closest_ech_file is None:
            continue
        # all TCP files (any location) of the closest measurement day
        tcp_date = common.extract_date(closest_ech_file).date()
        tcp_files = [f for f in ech_files if common.extract_date(f).date() == tcp_date]

        dfs.append(
            pl.scan_parquet(quic_file)
            .filter(ech.ech_accepted)
            .join(
                pl.scan_parquet(tcp_files).filter(ech.ech_accepted),
                on=C.target_sld,
                how="anti",
            )
            .select(C.measurement, C.location, C.ech_public_name, C.target_sld)
            .unique()
            .with_columns(pl.col(C.target_sld).str.split(".").list.get(-1).alias("tld"))
            .collect()
        )
    pl.concat(dfs).write_parquet(dst_file)


def agg_meta_fbsbx_domains(time_range: TimeRange, dst_file: Path | None = None):

    if dst_file is None:
        dst_file = common.processed_file("meta_fbsbx_domains", time_range)

    df = (
        loader.ech()
        .filter(time_range.expr(), pl.col(C.ech_public_name) == config.PUBLIC_NAME_META)
        .group_by(
            pl.col(C.measurement).dt.date(),
            C.location,
            pl.col(C.target_sld).str.ends_with(".apps.fbsbx.com").alias("fbsbx"),
        )
        .agg(pl.col(C.target_sld).n_unique())
    )
    cv.sink_parquet(df, dst_file)
