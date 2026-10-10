from datetime import datetime
import json
from pathlib import Path

from loguru import logger
import polars as pl
from tqdm.auto import tqdm

from ech_discovery import config
from ech_discovery.data import loaders as loader
from ech_discovery.data.columns import Columns as C
from ech_discovery.data.enrichment import ech, ip


def calculate_cf_meta_domains(df: pl.DataFrame | pl.LazyFrame, dst_file):
    multi_ech = (
        df.group_by(C.target)
        .agg(pl.col(C.ech_public_name).unique(), pl.col(C.measurement).min())
        .filter(pl.col(C.ech_public_name).list.len() > 1)
    )
    # Domains cannot be hosted on Meta and Cloudflare
    sus_domains = multi_ech.filter(
        pl.col(C.ech_public_name).list.contains(config.PUBLIC_NAME_CLOUDFLARE),
        pl.col(C.ech_public_name).list.contains(config.PUBLIC_NAME_META),
    )
    sus_domains.select(C.target, C.measurement).lazy().sink_parquet(dst_file)


def calculate_multi_ech_domains(
    dst_file: Path = config.PROCESSED_DATA_DIR / "multi-ech-domains_all.pq.zst",
    dst_file_cf_meta: Path = config.PROCESSED_DATA_DIR
    / "multi-ech-domains_cloudflare_and_meta.pq.zst",
):
    zdns_files = loader.FileSelector(globs=[loader.zdns_glob]).get_files()
    ech_quic_files = loader.FileSelector(globs=[loader.ech_quic_glob]).get_files()
    ech_files = loader.FileSelector(globs=[loader.ech_glob]).get_files()

    # Need to use python sets to keep this memory friendly
    seen = set()
    frames = []

    for file in tqdm(ech_files + ech_quic_files + zdns_files):
        cur_df = pl.DataFrame()
        if file in zdns_files:
            cur_df = (
                pl.scan_parquet(file)
                .select(
                    pl.col(C.zdns_target).alias(C.target),
                    C.target_sld,
                    pl.col(C.ech_processed).list.get(0).struct.field(C.ech_public_name),
                    C.role,
                    C.location,
                    C.measurement,
                )
                .filter(pl.col(C.ech_public_name).is_not_null())
                .unique()
                .collect()
            )
        else:
            cur_df = (
                pl.scan_parquet(file)
                .filter(pl.col(C.ech_public_name).is_not_null(), ech.ech_accepted)
                .select(
                    C.target,
                    C.target_sld,
                    C.ech_public_name,
                    C.role,
                    C.location,
                    C.measurement,
                )
                .unique()
                .collect()
            )

        new_frames = [row for row in cur_df.iter_rows() if row[:5] not in seen]
        new_rows = [row[:5] for row in cur_df.iter_rows() if row[:5] not in seen]
        seen.update(new_rows)
        if new_rows:
            frames.append(pl.DataFrame(new_frames, schema=cur_df.schema, orient="row"))

    df = (
        pl.concat(frames)
        .sort(C.measurement)
        .unique(subset=[C.target, C.ech_public_name], keep="first")
    )
    df.write_parquet(dst_file)

    calculate_cf_meta_domains(df, dst_file_cf_meta)


def ns_snapshot_date(file: Path) -> datetime:
    return datetime.fromisoformat(file.name.removesuffix(".jsonl.zst").replace("_", ":"))


def latest_ns_snapshot(dir: Path = config.RAW_DATA_DIR / "tud" / "NS") -> Path:
    return max(dir.glob("*.jsonl.zst"), key=ns_snapshot_date)


def ns_snapshot_input_count(snapshot: Path) -> int | None:
    """Domain count the scan was seeded with, from the sidecar the scan writes (if any)."""
    criteria = snapshot.with_name(f"{snapshot.name.removesuffix('.jsonl.zst')}-criteria.json")
    if not criteria.is_file():
        return None
    return json.loads(criteria.read_text()).get("count")


def agg_cf_meta_ns_location(
    dst_file: Path = config.PROCESSED_DATA_DIR / "cf_meta_ns_location.pq.zst",
):
    """Cloudflare+Meta domain counts by whether any NS sits in an AS registered in Asia."""
    for required in (ip.LOCATION_MMDB, ip.ASN_MMDB, ip.LOCATION_PARQUET):
        if not required.is_file():
            logger.warning(f"{required} missing, skipping cf_meta_ns_location")
            return

    snapshot = latest_ns_snapshot()
    scanned = (
        pl.scan_ndjson(snapshot)
        .select(pl.col(C.zdns_target).alias(C.target))
        .filter(pl.col(C.target).is_not_null())
        .unique()
    )

    df = (
        pl.scan_ndjson(snapshot)
        .rename({C.zdns_target: C.target})
        .unnest("results")
        .unnest("NSLOOKUP")
        .unnest("data")
        .explode("servers")
        .unnest("servers")
        .filter(pl.col(C.ipv4_addresses).is_not_null(), pl.col(C.target).is_not_null())
        .select(C.target, C.ipv4_addresses)
        .explode(C.ipv4_addresses)
    )

    ip_addresses = ip.ip_lookup(df)
    continents = ip.country_continent().rename(
        {C.country: C.asn_country, C.continent: C.asn_continent}
    )

    resolved = (
        df.join(ip_addresses, how="left", on=C.ipv4_addresses, validate="m:1")
        .join(continents, how="left", on=C.asn_country, validate="m:1")
        .group_by(C.target)
        # ignore_nulls=False: NS addresses that all fail to geolocate stay unknown, not "not Asia"
        .agg((pl.col(C.asn_continent) == ip.ASIA).any(ignore_nulls=False).alias(C.asn_asia))
    )

    counts = (
        scanned.join(resolved, how="left", on=C.target, validate="1:1")
        .group_by(C.asn_asia)
        .agg(pl.len())
        .with_columns(
            pl.lit(ns_snapshot_date(snapshot))
            .dt.convert_time_zone("UTC")
            .dt.replace_time_zone(None)
            .alias(C.measurement)
        )
        .collect()
    )

    input_count = ns_snapshot_input_count(snapshot)
    if input_count is not None and input_count != counts[C.len].sum():
        logger.warning(
            f"{snapshot.name}: scanned {counts[C.len].sum()} domains, "
            f"criteria sidecar lists {input_count}"
        )

    counts.write_parquet(dst_file)
