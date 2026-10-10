from datetime import date
from pathlib import Path

from loguru import logger
import polars as pl
from tqdm.auto import tqdm

from ech_discovery import config
from ech_discovery.data import loaders as loader
from ech_discovery.data.aggregates import common
from ech_discovery.data.aggregates.common import cv
from ech_discovery.data.columns import Columns as C
from ech_discovery.data.enrichment import ech, ip
from ech_discovery.data.ingest.ech import with_error_reason
from ech_discovery.data.mapper import Strings
from ech_discovery.data.ranges import follow_domain_date

ech_not_accepted = pl.col(C.ech_accepted).is_null() | ~pl.col(C.ech_accepted)


def extract_follow_domains(
    focus_date: date = follow_domain_date,
    dst_file: Path = config.PROCESSED_DATA_DIR / "follow-ech-domains.pq.zst",
):
    """Extract the domains that accepted ECH on `focus_date`, to follow them over time."""
    df_ech = loader.ech_tcp_tls(limit_per_location=True, regex_filter="tud")
    follow_ech_domains = (
        df_ech.filter(pl.col(C.measurement).dt.date() == focus_date, ech.ech_accepted)
        .select(C.target)
        .unique(C.target)
    )
    cv.sink_parquet(follow_ech_domains, dst_file)

    return dst_file


def error_stats(file: Path, df_domains: pl.LazyFrame) -> pl.DataFrame:
    df = (
        loader.without_multi_ech_domains(pl.scan_parquet(file))
        .join(df_domains, on=C.target, how="semi")
        .pipe(with_error_reason)
        .pipe(common.with_ech_in_dns, file, on=C.target)
    )
    stats = (
        df.group_by(C.measurement, C.location, C.error_reason, Strings.ech_in_dns)
        .agg(pl.col(C.target).drop_nulls().n_unique().alias(C.target))
        .collect()
    )
    return stats


def aggregate_error_stats(
    dst_file: Path = config.PROCESSED_DATA_DIR / "error_statistics_followed_domains.pq.zst",
):
    follow_domains = cv.load_data("follow-ech-domains")

    files = loader.FileSelector(globs=[loader.ech_glob]).get_files()
    dfs = []
    for file in tqdm(files):
        dfs.append(error_stats(file, follow_domains))

    pl.concat(dfs).write_parquet(dst_file)


def _failed_follow_ech(file: Path, df_domains: pl.LazyFrame) -> pl.LazyFrame:
    """Failed ECH attempts among the followed domains in one file, error reason extracted."""
    return (
        loader.without_multi_ech_domains(pl.scan_parquet(file).filter(ech_not_accepted))
        .join(df_domains, on=C.target, how="semi")
        .pipe(with_error_reason)
    )


def agg_follow_error_tlds(
    dst_file: Path = config.PROCESSED_DATA_DIR / "follow_error_tlds.pq.zst",
):
    """Failed follow requests per (measurement, location, error reason, TLD)."""
    follow_domains = cv.load_data("follow-ech-domains")

    tld_share = (
        follow_domains.select(pl.col(C.target).str.split(".").list.get(-1).alias("tld"))
        .group_by("tld")
        .agg(pl.len())
        .select("tld", (pl.col(C.len) / pl.col(C.len).sum()).alias("total_share"))
        .collect()
    )

    files = loader.FileSelector(globs=[loader.ech_glob]).get_files()
    dfs = []
    for file in tqdm(files):
        dfs.append(
            _failed_follow_ech(file, follow_domains)
            .with_columns(pl.col(C.target).str.split(".").list.get(-1).alias("tld"))
            .group_by(C.measurement, C.location, C.error_reason, "tld")
            .agg(pl.col(C.target).drop_nulls().n_unique().alias(C.len))
            .collect()
        )

    df = pl.concat(dfs).join(tld_share, on="tld", how="left", validate="m:1")
    cv.write_parquet(df, dst_file)


def agg_follow_error_asn(
    dst_file: Path = config.PROCESSED_DATA_DIR / "follow_error_asn.pq.zst",
):
    """Failed follow requests per (measurement, location, error reason, anchor-IP ASN)."""
    for required in (ip.LOCATION_MMDB, ip.ASN_MMDB):
        if not required.is_file():
            logger.warning(f"{required} missing, skipping follow_error_asn")
            return

    follow_domains = cv.load_data("follow-ech-domains")
    files = loader.FileSelector(globs=[loader.ech_glob]).get_files()

    unique_ips = pl.concat(
        [
            _failed_follow_ech(file, follow_domains)
            .select(pl.col(C.tls_handshake_anchor_ip).unique())
            .drop_nulls()
            .collect()
            for file in tqdm(files, desc="collecting anchor IPs")
        ]
    ).unique()
    # collect instead of sink: the maxmind lookups (map_elements) do not stream
    ip_addresses = ip.ip_lookup(unique_ips.lazy(), col=C.tls_handshake_anchor_ip).collect()

    dfs = []
    for file in tqdm(files, desc="aggregating per-file ASN stats"):
        dfs.append(
            _failed_follow_ech(file, follow_domains)
            .select(C.measurement, C.location, C.error_reason, C.tls_handshake_anchor_ip, C.target)
            .join(ip_addresses.lazy(), on=C.tls_handshake_anchor_ip, how="left", validate="m:1")
            .group_by(C.measurement, C.location, C.error_reason, C.asn, C.asn_name, C.asn_type)
            .agg(pl.col(C.target).drop_nulls().n_unique().alias(C.len))
            .collect()
        )

    pl.concat(dfs).write_parquet(dst_file)


def agg_retry_provided(
    dst_file: Path = config.PROCESSED_DATA_DIR / "retry_provided.pq.zst",
    dst_file_all_locations: Path = config.PROCESSED_DATA_DIR
    / "retry_provided_all_locations.pq.zst",
):
    """Domains that failed ECH but offered retry configs, per measurement date and location."""
    common.unique_domains_by_date(
        ech_not_accepted & (pl.col(C.retry_configs).list.len() > 0),
        dst_file,
        dst_file_all_locations,
    )
