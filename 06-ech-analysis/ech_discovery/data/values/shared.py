from datetime import date
import json
from pathlib import Path

from ndpi.value_store import ValueStore, fmt_date, fmt_eng, fmt_percent
import polars as pl

from ech_discovery import config
from ech_discovery.data import loaders as loader
from ech_discovery.data.aggregates.common import ech_with_dns_status, processed_file
from ech_discovery.data.columns import Columns as C
from ech_discovery.data.enrichment.ech import is_example_public_name
from ech_discovery.data.mapper import Strings
from ech_discovery.data.metrics import common as metrics_common
from ech_discovery.data.ranges import ALL, FOLLOWUP, MAIN
from ech_discovery.data.values.common import (
    and_join,
    measurement_location,
    pct_label,
)

ZGRAB2_DIR = config.RAW_DATA_DIR / measurement_location / "zgrab2"
ZGRAB2_TLS12 = "v771"
ZGRAB2_TLS13 = "v772"
ZGRAB2_CRITERIA_SUFFIX = "-criteria.json"
TLS_VERSION_UNSUPPORTED = "tls: protocol version not supported"


def _latest_zgrab2_tls_scan() -> tuple[Path, Path, date] | None:
    """Newest TLS 1.2/1.3 zgrab2 scan pair, with the snapshot date its targets came from."""
    scans = []
    for criteria_file in ZGRAB2_DIR.glob(f"{ZGRAB2_TLS12}_*{ZGRAB2_CRITERIA_SUFFIX}"):
        criteria = json.loads(criteria_file.read_text())
        if not criteria.get("count"):
            continue
        snapshot = date.fromisoformat(criteria["date"])
        stamp = criteria_file.name[len(ZGRAB2_TLS12) + 1 : -len(ZGRAB2_CRITERIA_SUFFIX)]
        tls12 = ZGRAB2_DIR / f"{ZGRAB2_TLS12}_{stamp}.jsonl.zst"
        tls13 = ZGRAB2_DIR / f"{ZGRAB2_TLS13}_{stamp}.jsonl.zst"
        if tls12.exists() and tls13.exists():
            scans.append((snapshot, stamp, tls12, tls13))
    if not scans:
        return None
    snapshot, _, tls12, tls13 = max(scans)
    return tls12, tls13, snapshot


def register_shared(store: ValueStore, total_stats: pl.LazyFrame) -> None:
    """Values that don't depend on the measurement time range."""
    store.register(
        "TotalMeasurementDurationMonths",
        round((MAIN.duration + FOLLOWUP.duration).days / (365.25 / 12)),
    )
    input_stats = loader.ech_input_stats()
    store.register(
        "TotalTargetDomains", input_stats.select(pl.col(C.target_total).max()), fmt=fmt_eng(1)
    )

    tls_scan = _latest_zgrab2_tls_scan()
    if tls_scan is not None:
        tls12_file, tls13_file, scan_snapshot = tls_scan
        store.register(
            "cloudflareEchQuicOnlyDate",
            scan_snapshot,
            fmt=fmt_date("%b %-d, %Y"),
        )
        scanned = pl.scan_ndjson(tls12_file)
        tls12_only = scanned.filter(pl.col(C.error).is_null()).join(
            pl.scan_ndjson(tls13_file).filter(
                pl.col(C.error).str.contains(TLS_VERSION_UNSUPPORTED, literal=True)
            ),
            on=C.domain,
            how="semi",
        )
        store.register(
            "cloudflareEchQuicOnlyProbed",
            scanned.select(pl.col(C.domain).drop_nulls().n_unique()),
            fmt=fmt_eng(1),
        )
        store.register(
            "cloudflareEchQuicOnlyRuShare",
            pl.scan_parquet(processed_file("quic_only_domains", ALL))
            .filter(
                pl.col(C.ech_public_name) == config.PUBLIC_NAME_CLOUDFLARE,
                pl.col(C.location) == measurement_location,
                pl.col(C.measurement).dt.date() == scan_snapshot,
            )
            .select(
                pl.col(C.target_sld).filter(pl.col("tld") == "ru").drop_nulls().n_unique()
                / pl.col(C.target_sld).drop_nulls().n_unique()
                * 100
            ),
            fmt=fmt_percent(digits=0),
        )
        store.register(
            "cloudflareEchQuicOnlyTls12",
            tls12_only.select(pl.col(C.domain).drop_nulls().n_unique()),
            fmt=fmt_eng(1),
        )
        store.register(
            "cloudflareEchQuicOnlyTls12Share",
            tls12_only.select(pl.col(C.domain).drop_nulls().n_unique().alias(C.len))
            .join(
                scanned.select(pl.col(C.domain).drop_nulls().n_unique().alias("scanned")),
                how="cross",
            )
            .select(pl.col(C.len) / pl.col("scanned") * 100),
            fmt=fmt_percent(digits=1),
        )

        wo_cf_meta = ech_with_dns_status(
            limit_per_location=True,
            regex_filter=f"{measurement_location}/{scan_snapshot}",
            limit=1,
        ).filter(~pl.col(C.ech_public_name).is_in(config.MAIN_ECH_PUBLIC_NAMES))
        store.register(
            "echAcceptedSldWoCloudflareAndMetaInDns",
            wo_cf_meta.select(
                pl.col(C.target_sld).filter(pl.col(Strings.ech_in_dns)).drop_nulls().n_unique()
            ),
        )
        store.register(
            "echAcceptedSldWoCloudflareAndMetaNoDns",
            wo_cf_meta.select(
                pl.col(C.target_sld).filter(~pl.col(Strings.ech_in_dns)).drop_nulls().n_unique()
            ),
        )
        store.register(
            "echAcceptedSldWoCloudflareAndMetaInDnsShare",
            wo_cf_meta.select(
                pl.col(C.target_sld).filter(pl.col(Strings.ech_in_dns)).drop_nulls().n_unique()
                / pl.col(C.target_sld).drop_nulls().n_unique()
                * 100
            ),
            fmt=fmt_percent(digits=0),
        )
        store.register(
            "echAcceptedSldWoCloudflareAndMetaNoDnsShare",
            wo_cf_meta.select(
                pl.col(C.target_sld).filter(~pl.col(Strings.ech_in_dns)).drop_nulls().n_unique()
                / pl.col(C.target_sld).drop_nulls().n_unique()
                * 100
            ),
            fmt=fmt_percent(digits=0),
        )

    store.register(
        "echPublicNameTotalWoMetaCloudflare",
        metrics_common.latest_of(
            total_stats.filter(
                ~pl.col(C.ech_public_name).is_in(config.MAIN_ECH_PUBLIC_NAMES_ALL),
                pl.col(C.ech_public_name) != config.PUBLIC_NAME_NOT_CLOUDFLARE_META,
            ),
            ALL,
        ).select(pl.col(C.ech_public_name).drop_nulls().n_unique()),
    )
    store.register(
        "echPublicNameTotalWoMetaCloudflareNordvpn",
        metrics_common.latest_of(
            total_stats.filter(
                ~pl.col(C.ech_public_name).is_in(config.MAIN_ECH_PUBLIC_NAMES_ALL),
                pl.col(C.ech_public_name) != config.PUBLIC_NAME_NOT_CLOUDFLARE_META,
                ~is_example_public_name(),
            ),
            ALL,
        ).select(pl.col(C.ech_public_name).drop_nulls().n_unique()),
    )

    ns_location = pl.scan_parquet(config.PROCESSED_DATA_DIR / "cf_meta_ns_location.pq.zst")
    store.register(
        "cloudflareAndMetaDomainsNsLocationShareAsianAses",
        ns_location.select(
            pl.col(C.len).filter(pl.col(C.asn_asia).fill_null(False)).sum()
            / pl.col(C.len).sum()
            * 100
        ),
        fmt=fmt_percent(digits=1),
    )
    store.register(
        "cloudflareAndMetaDomainsNsLocationShareAsianAsesResolved",
        ns_location.select(
            pl.col(C.len).filter(pl.col(C.asn_asia).fill_null(False)).sum()
            / pl.col(C.len).filter(pl.col(C.asn_asia).is_not_null()).sum()
            * 100
        ),
        fmt=fmt_percent(digits=1),
    )
    store.register(
        "cloudflareAndMetaDomainsNsLocationShareUnresolved",
        ns_location.select(
            pl.col(C.len).filter(pl.col(C.asn_asia).is_null()).sum() / pl.col(C.len).sum() * 100
        ),
        fmt=fmt_percent(digits=1),
    )

    cdn_domains = pl.scan_parquet(config.PROCESSED_DATA_DIR / "cdn_domains.pq.zst")
    store.register(
        "cdnDomainsMultiCdnShare",
        cdn_domains.select((pl.col(C.asn_cdn).list.len() > 1).sum() / pl.len() * 100),
        fmt=fmt_percent(digits=1),
    )
    store.register(
        "cdnDomainsTopPrimaryWoCloudflare",
        cdn_domains.filter(pl.col(C.asn_cdn).list.len() == 1)
        .explode(C.asn_cdn)
        .group_by(C.asn_cdn)
        .agg(pl.len())
        .drop_nulls(C.asn_cdn)
        .filter(pl.col(C.asn_cdn) != "Cloudflare")
        .join(cdn_domains.select(pl.len().alias("total")), how="cross")
        .with_columns((pl.col(C.len) / pl.col("total") * 100).alias(C.len_percent))
        .top_k(3, by=C.len_percent)
        .sort(C.len_percent, descending=True)
        .select(pct_label(pl.col(C.asn_cdn)).alias("label"))
        .pipe(and_join),
    )

    ark_nodes = pl.scan_ndjson(config.RAW_DATA_DIR / "ark" / "ark-nodes.jsonl")
    store.register("arkAsns", ark_nodes.select(pl.col("asn4").drop_nulls().n_unique()))
    store.register(
        "arkCountries",
        # Nodes from the CAIDA API have no cc, but their place ends in the country code.
        ark_nodes.select(pl.coalesce(pl.col("cc"), pl.col("place").str.slice(-2)).n_unique()),
    )

    ark_timing = pl.scan_parquet(config.PROCESSED_DATA_DIR / "ark_timing.pq.zst")
    store.register(
        "arkMedianDifference",
        ark_timing.filter(pl.col("group") == "main").select(
            pl.col("median_ech_minus_tls_rtt").round(1)
        ),
    )
    store.register(
        "arkMedianDifferenceCloudflare",
        ark_timing.filter(pl.col("group") == "cloudflare").select(
            pl.col("median_ech_minus_tls_rtt").round(1)
        ),
    )
    store.register(
        "arkMedianDifferenceMeta",
        ark_timing.filter(pl.col("group") == "meta").select(
            pl.col("median_ech_minus_tls_rtt").round(1)
        ),
    )
