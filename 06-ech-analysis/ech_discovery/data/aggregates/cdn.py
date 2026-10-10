from pathlib import Path

from loguru import logger
import polars as pl

from ech_discovery import config
from ech_discovery.data.columns import Columns as C
from ech_discovery.data.enrichment.ip import ASN_MMDB, LOCATION_MMDB, ip_lookup
from ech_discovery.data.mapper import df_cdns


def get_domain_and_asn_count(glob: str = "2026-08*.jsonl.zst") -> pl.DataFrame:
    """One row per (domain, resolved IP, ASN, matched CDN) from the raw A-lookup snapshot."""
    df = (
        pl.read_ndjson(list((config.RAW_DATA_DIR / "tud" / "A").glob(glob)))
        .unnest(C.results)
        .unnest(C.alookup)
        .unnest(C.data)
        .explode(C.ipv4_addresses, empty_as_null=True)
    )
    ip_addresses = ip_lookup(df)
    return df.join(
        ip_addresses.with_columns(pl.col(C.asn).str.slice(2).cast(pl.UInt32)),
        on=C.ipv4_addresses,
        validate="m:1",
        how="left",
    ).join(df_cdns, on=C.asn, how="left", validate="m:1")


def agg_cdn_domains(
    dst_file: Path = config.PROCESSED_DATA_DIR / "cdn_domains.pq.zst",
    glob: str = "2026-08*.jsonl.zst",
):
    for required in (LOCATION_MMDB, ASN_MMDB):
        if not required.is_file():
            logger.warning(f"{required} missing, skipping cdn_domains")
            return

    df = (
        get_domain_and_asn_count(glob)
        .group_by(C.zdns_target)
        .agg(pl.col(C.asn_cdn).drop_nulls().unique())
    )
    df.write_parquet(dst_file)
